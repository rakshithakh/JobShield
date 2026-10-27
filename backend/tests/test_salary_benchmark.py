import io
import logging

import httpx
import pytest

import app.services.salary_benchmark as sb
from app.logging_config import configure_logging
from app.services.pipeline import run_pipeline
from app.services.salary import analyze_salary_live
from app.services.salary_benchmark import AdzunaSalaryBenchmarks, normalise_query, parse_histogram, weighted_percentile
from app.services.types import AnalysisInput
from tests.conftest import make_client, make_detector, make_settings

# 400 listings: 10th pct = 200k, median = 300k, 90th pct = 500k (annual INR)
GOOD = {"histogram": {"150000": 20, "200000": 60, "250000": 100, "300000": 100, "400000": 60, "500000": 40, "700000": 20}}


def prov(handler, **kw):
    s = make_settings(adzuna_app_id="id", adzuna_app_key="SECRET-ADZ-KEY", **kw)
    return AdzunaSalaryBenchmarks(s, httpx.Client(transport=httpx.MockTransport(handler)))


def ok(body=GOOD):
    return lambda r: httpx.Response(200, json=body)


def test_weighted_percentile_and_parsing():
    pts = parse_histogram(GOOD)
    assert weighted_percentile(pts, 0.5) == 300000 and weighted_percentile(pts, 0.1) == 200000
    assert weighted_percentile(pts, 0.9) == 500000
    assert parse_histogram({"histogram": {"abc": 5, "-1": 3, "100": 0, "200": "x", "300": 4}}) == [(300.0, 4)]
    assert parse_histogram({"nope": 1}) is None and parse_histogram([1]) is None


def test_query_is_normalised_and_bounded():
    assert normalise_query("  Data  Entry!! Operator ") == "data entry operator"
    assert len(normalise_query("x" * 500)) == 100


def test_not_configured_and_disabled():
    assert AdzunaSalaryBenchmarks(make_settings()).lookup("dev")[1].status == "not_configured"
    off = AdzunaSalaryBenchmarks(make_settings(adzuna_app_id="i", adzuna_app_key="k", adzuna_salary_benchmarks=False))
    assert off.lookup("dev")[1].status == "not_configured"


def test_good_histogram_gives_percentile_benchmark():
    b, p = prov(ok()).lookup("Data Entry")
    assert (b.low, b.median, b.high, b.listings) == (200000, 300000, 500000, 400) and p.status == "ok"


def test_request_sends_only_the_job_title_and_expected_params():
    seen = []
    prov(lambda r: seen.append(r) or httpx.Response(200, json=GOOD)).lookup("Data Entry")
    assert seen[0].url.path == "/v1/api/jobs/in/histogram"
    assert dict(seen[0].url.params) == {"app_id": "id", "app_key": "SECRET-ADZ-KEY", "what": "data entry", "content-type": "application/json"}


@pytest.mark.parametrize("body", [{"histogram": {"300000": 5, "400000": 5}}, {"histogram": {"1": 100}}, {"histogram": {}}])
def test_thin_data_is_not_used(body):
    b, p = prov(ok(body)).lookup("rare role")
    assert b is None and p.status == "ok" and "too few" in p.detail


@pytest.mark.parametrize("handler", [lambda r: httpx.Response(429), lambda r: httpx.Response(500), lambda r: httpx.Response(200, text="<html>"),
                                     lambda r: httpx.Response(200, json={"histogram": "x"}), lambda r: httpx.Response(200, json=[1])])
def test_failures_are_reported_not_hidden(handler):
    b, p = prov(handler).lookup("dev")
    assert b is None and p.status == "failed"


def test_timeout_is_a_failure():
    def boom(r):
        raise httpx.ReadTimeout("slow")
    assert prov(boom).lookup("dev")[1].status == "failed"


def test_cache_saves_api_calls_and_expires(monkeypatch):
    calls = []
    p = prov(lambda r: calls.append(1) or httpx.Response(200, json=GOOD))
    p.lookup("Data Entry"); p.lookup("data   entry"); p.lookup("DATA ENTRY!")
    assert len(calls) == 1                                   # all normalise to one key
    assert p.lookup("data entry")[1].detail.endswith("(cached)")
    p.lookup("python developer")
    assert len(calls) == 2
    real = sb.time.monotonic
    monkeypatch.setattr(sb.time, "monotonic", lambda: real() + sb.CACHE_TTL_SECONDS + 1)
    p.lookup("data entry")
    assert len(calls) == 3


def test_failures_are_cached_briefly_to_avoid_request_storms(monkeypatch):
    calls = []
    p = prov(lambda r: calls.append(1) or httpx.Response(429))
    for _ in range(5):
        p.lookup("dev")
    assert len(calls) == 1
    real = sb.time.monotonic
    monkeypatch.setattr(sb.time, "monotonic", lambda: real() + sb.FAILURE_TTL_SECONDS + 1)
    p.lookup("dev")
    assert len(calls) == 2


def test_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(sb, "MAX_CACHE_ENTRIES", 5)
    p = prov(ok())
    for i in range(20):
        p.lookup(f"role {i}")
    assert len(p._cache) <= 5


# ---- how the benchmark changes the salary check
def live(text, title, provider):
    return analyze_salary_live(title, text, provider)


def test_real_benchmark_replaces_the_table_and_names_its_source():
    sigs, paths = live("Data entry, earn Rs 90000 per month", "Data Entry", prov(ok()))      # 10.8 LPA vs p90 5 LPA -> > 2x
    assert sigs[0].code == "salary:unrealistic_high" and sigs[0].points == 30
    assert "Adzuna" in sigs[0].explanation and "400 listings" in sigs[0].explanation and "unsourced" not in sigs[0].explanation
    assert paths[0].name == "adzuna_salary" and paths[0].status == "ok"


def test_real_benchmark_in_range_adds_nothing():
    sigs, _ = live("Data entry, earn Rs 25000 per month", "Data Entry", prov(ok()))          # 3 LPA = median
    assert sigs[0].code == "salary:in_range" and sigs[0].points == 0


def test_a_real_range_can_disagree_with_the_old_table():
    """The hand table says 'software engineer' tops out far lower than this market data does."""
    high_market = {"histogram": {str(x): 50 for x in (800000, 1200000, 1800000, 2500000, 3500000)}}
    text = "software engineer CTC 30 LPA"
    table = live(text, "Software Engineer", None)[0][0]
    market = live(text, "Software Engineer", prov(ok(high_market)))[0][0]
    assert table.points > market.points == 0


def test_falls_back_to_table_when_benchmark_unavailable():
    sigs, paths = live("Data entry, earn Rs 90000 per month", "Data Entry", prov(lambda r: httpx.Response(500)))
    assert sigs[0].points > 0 and "unsourced" in sigs[0].explanation and paths[0].status == "failed"


def test_no_api_call_when_the_text_has_no_salary():
    calls = []
    sigs, paths = live("Great team, apply by email", "Data Entry", prov(lambda r: calls.append(1) or httpx.Response(200, json=GOOD)))
    assert not calls and sigs[0].code == "salary:none" and paths[0].status == "skipped"


def test_pipeline_records_the_path_and_never_fails_on_provider_crash():
    class Boom:
        def lookup(self, q):
            raise RuntimeError("x")
    det = make_detector([])
    det.salary_benchmarks = prov(ok())
    r = run_pipeline(AnalysisInput("Data entry job. Earn Rs 90000 per month. Contact me", job_title="Data Entry"), det)
    assert any(p.name == "adzuna_salary" and p.status == "ok" for p in r.detection_paths)
    det.salary_benchmarks = Boom()
    r2 = run_pipeline(AnalysisInput("Data entry job. Earn Rs 90000 per month. Contact me", job_title="Data Entry"), det)
    assert any(p.name == "salary" and p.status == "failed" for p in r2.detection_paths)       # recorded, analysis still returned


def test_end_to_end_api_uses_the_benchmark():
    det = make_detector([])
    det.salary_benchmarks = prov(ok())
    c = make_client(detector=det)
    j = c.post("/api/v1/analyses", json={"job_text": "Data entry job, earn Rs 90000 per month, mail hr@acme.example.com", "job_title": "Data Entry"},
               headers={"X-Session-Token": "t" * 40}).json()
    sal = next(s for s in j["signals"] if s["source"] == "salary")
    assert sal["points"] == 30 and "Adzuna" in sal["explanation"]
    assert any(p["name"] == "adzuna_salary" for p in j["detection_paths"])


def test_api_key_never_logged():
    configure_logging()
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    logging.getLogger().addHandler(h)
    try:
        prov(ok()).lookup("dev")
    finally:
        logging.getLogger().removeHandler(h)
    assert "SECRET-ADZ-KEY" not in buf.getvalue()
