import io
import logging

import httpx
import pytest

from app.logging_config import configure_logging
from app.services.company import Mca21Provider
from app.services.listings import AdzunaListingProvider, _same_company
from tests.conftest import SCAM_TEXT, make_client, make_detector, make_settings


def adz(handler, **kw):
    s = make_settings(adzuna_app_id="id", adzuna_app_key="SECRET-ADZ-KEY", **kw)
    return AdzunaListingProvider(s, httpx.Client(transport=httpx.MockTransport(handler)))


def results(*names, url="https://www.adzuna.in/land/ad/1"):
    return httpx.Response(200, json={"results": [{"company": {"display_name": n}, "redirect_url": url} for n in names]})


def test_not_configured_is_explicit():
    c, p = AdzunaListingProvider(make_settings()).lookup("Acme", "Dev")
    assert c.status == "not_configured" and p.status == "not_configured"


def test_no_company_skips_without_calling_api():
    called = []
    c, p = adz(lambda r: called.append(r) or results()).lookup("  ", "Dev")
    assert c.status == "not_provided" and p.status == "skipped" and not called


def test_match_is_informational_and_links_source():
    c, p = adz(lambda r: results("Acme Widgets Pvt Ltd")).lookup("Acme Widgets", "Dev")
    assert c.status == "listing_found" and c.source_url == "https://www.adzuna.in/land/ad/1" and p.status == "ok"
    assert "does not confirm" in c.summary


def test_no_match_is_inconclusive_wording():
    c, _ = adz(lambda r: results("Totally Different Ltd")).lookup("Acme", "Dev")
    assert c.status == "listing_not_found" and "inconclusive" in c.summary


def test_non_http_redirect_url_is_dropped():
    c, _ = adz(lambda r: results("Acme", url="javascript:alert(1)")).lookup("Acme", "Dev")
    assert c.status == "listing_found" and c.source_url is None


@pytest.mark.parametrize("handler", [
    lambda r: httpx.Response(429), lambda r: httpx.Response(500), lambda r: httpx.Response(200, text="not json"),
    lambda r: httpx.Response(200, json={"results": "nope"}), lambda r: httpx.Response(200, json=[1]),
])
def test_failures_become_unavailable(handler):
    c, p = adz(handler).lookup("Acme", "Dev")
    assert c.status == "unavailable" and p.status == "failed"


def test_timeout_becomes_unavailable():
    def boom(r):
        raise httpx.ReadTimeout("slow")
    assert adz(boom).lookup("Acme", "Dev")[0].status == "unavailable"


def test_company_matching_ignores_suffixes_but_not_extra_words():
    assert _same_company("Infosys Limited", "Infosys")
    assert not _same_company("Ola", "Ola Earn Fast Jobs")


def test_listing_result_never_changes_the_score():
    base = make_client(detector=make_detector())
    det = make_detector()
    det.listings = adz(lambda r: results("Acme"))
    with_listing = make_client(detector=det)
    h = {"X-Session-Token": "t" * 40}
    body = {"job_text": SCAM_TEXT, "company_name": "Acme"}
    a = base.post("/api/v1/analyses", json=body, headers=h).json()
    b = with_listing.post("/api/v1/analyses", json=body, headers=h).json()
    assert a["risk_score"] == b["risk_score"]
    assert any(c["provider"] == "adzuna_listing" and c["status"] == "listing_found" for c in b["company_checks"])


def test_listing_crash_does_not_fail_the_analysis():
    det = make_detector()

    class Boom:
        def lookup(self, *a):
            raise RuntimeError("x")
    det.listings = Boom()
    r = make_client(detector=det).post("/api/v1/analyses", json={"job_text": SCAM_TEXT, "company_name": "Acme"}, headers={"X-Session-Token": "t" * 40})
    assert r.status_code == 201


@pytest.mark.parametrize("make", ["adzuna", "mca"])
def test_api_keys_never_reach_the_logs(make):
    configure_logging()
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    logging.getLogger().addHandler(handler)
    try:
        ok = httpx.MockTransport(lambda r: httpx.Response(200, json={"results": [], "records": []}))
        if make == "adzuna":
            AdzunaListingProvider(make_settings(adzuna_app_id="id", adzuna_app_key="SECRET-ADZ-KEY"), httpx.Client(transport=ok)).lookup("Acme", "Dev")
        else:
            Mca21Provider(make_settings(mca_api_key="SECRET-ADZ-KEY"), httpx.Client(transport=ok)).lookup("Acme")
    finally:
        logging.getLogger().removeHandler(handler)
    assert "SECRET-ADZ-KEY" not in buf.getvalue()
