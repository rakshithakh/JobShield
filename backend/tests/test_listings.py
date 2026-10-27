import httpx
import pytest

from app.services.listings import AdzunaListingProvider
from app.services.pipeline import Detector, run_pipeline
from app.services.types import AnalysisInput
from tests.conftest import FakePredictor, make_detector, make_settings


def prov(handler, **kw):
    s = make_settings(adzuna_app_id="id", adzuna_app_key="key", **kw)
    return AdzunaListingProvider(s, httpx.Client(transport=httpx.MockTransport(handler)))


def ok(results):
    return lambda r: httpx.Response(200, json={"count": len(results), "results": results})


def test_not_configured_is_reported_not_faked():
    c, p = AdzunaListingProvider(make_settings()).lookup("Acme", "Dev")
    assert c.status == "not_configured" and p.status == "not_configured"


def test_match_found_is_informational_and_url_checked():
    c, p = prov(ok([{"company": {"display_name": "ACME Widgets Pvt Ltd"}, "redirect_url": "https://www.adzuna.in/land/ad/1"}])).lookup("Acme Widgets", "Accountant")
    assert c.status == "listing_found" and c.source_url == "https://www.adzuna.in/land/ad/1" and "does not confirm" in c.summary


def test_dangerous_redirect_url_is_dropped():
    c, _ = prov(ok([{"company": {"display_name": "Acme"}, "redirect_url": "javascript:alert(1)"}])).lookup("Acme", "Dev")
    assert c.status == "listing_found" and c.source_url is None


def test_no_match_is_inconclusive():
    c, _ = prov(ok([{"company": {"display_name": "Other Co"}}])).lookup("Acme", "Dev")
    assert c.status == "listing_not_found" and "inconclusive" in c.summary


def test_query_sends_keys_only_to_adzuna_and_limits_country():
    seen = []
    prov(lambda r: (seen.append(r), httpx.Response(200, json={"results": []}))[1], adzuna_country="../evil").lookup("Acme", "Dev")
    assert seen[0].url.host == "api.adzuna.com" and "/jobs/evil/" in seen[0].url.path or "/jobs/in/" in seen[0].url.path


@pytest.mark.parametrize("handler", [lambda r: httpx.Response(429), lambda r: httpx.Response(500), lambda r: httpx.Response(200, text="x"),
                                      lambda r: httpx.Response(200, json={"results": "nope"})])
def test_failures_become_unavailable(handler):
    c, p = prov(handler).lookup("Acme", "Dev")
    assert c.status == "unavailable" and p.status == "failed"


def test_listing_never_changes_score():
    base = make_detector([FakePredictor(0.3)])
    with_l = Detector(ml=base.ml, registry=base.registry, listings=prov(ok([{"company": {"display_name": "Acme"}}])))
    a = run_pipeline(AnalysisInput("Pay Rs 999 registration fee now", "Acme", "Dev"), base)
    b = run_pipeline(AnalysisInput("Pay Rs 999 registration fee now", "Acme", "Dev"), with_l)
    assert a.risk_score == b.risk_score and any(c.provider == "adzuna_listing" for c in b.company_checks)
