import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db import repository as repo
from app.db.models import Analysis, AnalysisSignal
from tests.conftest import REAL_TEXT, SCAM_TEXT, FakePredictor, make_client, make_detector, make_settings
from tests.test_url_and_upload import make_pdf

URL = "/api/v1/analyses"


def post(client, auth, **body):
    return client.post(URL, json=body, headers=auth)


def test_health_reports_paths_and_db(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok" and j["database"] == "ok"
    names = {p["name"]: p["status"] for p in j["detection_paths"]}
    assert names["distilbert"] == "not_configured" and names["company_search"] == "not_configured"
    assert r.headers["x-request-id"] and r.headers["x-content-type-options"] == "nosniff"


def test_health_reports_online_company_search_disabled():
    client = make_client(settings=make_settings())
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    company_search = next(p for p in r.json()["detection_paths"] if p["name"] == "company_search")
    assert company_search["status"] == "not_configured"
    assert "online company search is disabled" in company_search["detail"]


def test_create_text_analysis_full_schema(client, auth):
    r = post(client, auth, job_text=SCAM_TEXT, company_name="Nexgen Solutions", job_title="Data Entry Operator")
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["risk_level"] == "high" and j["risk_score"] >= 60 and j["status"] == "completed"
    assert {"rules", "scoring", "model"} <= set(j["versions"])
    assert j["signals"] and all("explanation" in s for s in j["signals"])
    assert j["company_status"] == "name_heuristic"
    assert any(p["name"] == "mca21" and p["status"] == "not_configured" for p in j["detection_paths"])
    assert j["limitations"] and j["recommendations"]
    assert "job_text" not in j and "input_text" not in j          # raw input never echoed back
    assert uuid.UUID(j["id"])


def test_real_posting_low_and_company_unknown_not_fraud(client, auth):
    j = post(client, auth, job_text=REAL_TEXT.replace("Infosys", "Zeta Labs").replace("infosys", "zetalabs"), company_name="Zeta Labs").json()
    assert j["risk_level"] == "low" and j["company_status"] == "unknown"


@pytest.mark.parametrize("body,field", [
    ({}, None), ({"job_text": "short"}, "job_text"), ({"job_text": "x" * 20001}, "job_text"),
    ({"job_text": "a" * 40, "job_url": "https://example.com"}, None), ({"job_text": "   "}, None),
    ({"job_text": "a" * 40, "company_name": "c" * 201}, "company_name"),
])
def test_validation_errors_are_structured(client, auth, body, field):
    r = post(client, auth, **body)
    assert r.status_code == 422
    e = r.json()["error"]
    assert e["code"] == "validation_error" and e["request_id"]
    assert "Traceback" not in r.text


def test_requires_session_token(client):
    for headers in ({}, {"X-Session-Token": "short"}, {"X-Session-Token": "bad token with spaces " * 3}):
        assert client.get(URL, headers=headers).status_code == 401
        assert client.post(URL, json={"job_text": SCAM_TEXT}, headers=headers).status_code == 401


def test_cross_user_access_is_denied(client):
    a, b = {"X-Session-Token": secrets.token_urlsafe(32)}, {"X-Session-Token": secrets.token_urlsafe(32)}
    aid = post(client, a, job_text=SCAM_TEXT).json()["id"]
    assert client.get(f"{URL}/{aid}", headers=a).status_code == 200
    assert client.get(f"{URL}/{aid}", headers=b).status_code == 404            # not 403: existence not revealed
    assert client.delete(f"{URL}/{aid}", headers=b).status_code == 404
    assert client.get(URL, headers=b).json()["total"] == 0
    assert client.get("/api/v1/dashboard/summary", headers=b).json()["total_analyses"] == 0
    assert client.get(f"{URL}/{aid}", headers=a).status_code == 200            # still intact


def test_unknown_and_malformed_ids(client, auth):
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=auth).status_code == 404
    r = client.get(f"{URL}/not-a-uuid", headers=auth)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_pagination_filter_search_sort(client, auth):
    for i in range(7):
        post(client, auth, job_text=SCAM_TEXT, company_name=f"Nexgen {i}", job_title="Data Entry")
    for i in range(3):
        post(client, auth, job_text="We are hiring a Python developer in Pune, 3 years experience required.", company_name=f"Quiet Co {i}")
    p1 = client.get(URL, params={"page_size": 4}, headers=auth).json()
    assert p1["total"] == 10 and p1["total_pages"] == 3 and len(p1["items"]) == 4
    p3 = client.get(URL, params={"page_size": 4, "page": 3}, headers=auth).json()
    assert len(p3["items"]) == 2
    ids = {i["id"] for pg in (1, 2, 3) for i in client.get(URL, params={"page_size": 4, "page": pg}, headers=auth).json()["items"]}
    assert len(ids) == 10                                                         # stable, no overlaps
    assert client.get(URL, params={"risk_level": "high"}, headers=auth).json()["total"] == 7
    assert client.get(URL, params={"q": "quiet"}, headers=auth).json()["total"] == 3
    assert client.get(URL, params={"q": "%"}, headers=auth).json()["total"] == 0   # wildcard is escaped
    top = client.get(URL, params={"sort": "risk_desc"}, headers=auth).json()["items"][0]
    assert top["risk_level"] == "high"
    assert client.get(URL, params={"page_size": 500}, headers=auth).status_code == 422
    assert client.get(URL, params={"risk_level": "bogus"}, headers=auth).status_code == 422


def test_sql_injection_string_is_inert(client, auth):
    post(client, auth, job_text=SCAM_TEXT, company_name="Acme")
    r = client.get(URL, params={"q": "' OR 1=1 --"}, headers=auth)
    assert r.status_code == 200 and r.json()["total"] == 0


def test_dashboard_matches_real_data(client, auth):
    empty = client.get("/api/v1/dashboard/summary", headers=auth).json()
    assert empty["total_analyses"] == 0 and empty["average_risk_score"] is None and empty["recent"] == []
    post(client, auth, job_text=SCAM_TEXT, company_name="Nexgen")
    post(client, auth, job_text="Python developer wanted in Pune. 3 years experience needed with Django.")
    s = client.get("/api/v1/dashboard/summary", headers=auth).json()
    assert s["total_analyses"] == 2 and s["risk_distribution"]["high"] == 1 and s["risk_distribution"]["low"] == 1
    assert len(s["recent"]) == 2 and s["average_risk_score"] > 0


def test_delete_removes_children(client, auth):
    aid = post(client, auth, job_text=SCAM_TEXT).json()["id"]
    assert client.delete(f"{URL}/{aid}", headers=auth).status_code == 204
    assert client.get(f"{URL}/{aid}", headers=auth).status_code == 404
    with client.app.state.session_factory() as db:
        assert db.execute(select(AnalysisSignal)).first() is None


def test_input_text_not_stored_by_default_and_hash_kept(client, auth):
    post(client, auth, job_text=SCAM_TEXT)
    with client.app.state.session_factory() as db:
        a = db.execute(select(Analysis)).scalar_one()
        assert a.input_text is None and a.input_sha256 and a.input_length == len(SCAM_TEXT)


def test_retention_stores_then_purges():
    c = make_client(make_settings(input_text_retention_days=1))
    h = {"X-Session-Token": secrets.token_urlsafe(32)}
    j = c.post(URL, json={"job_text": SCAM_TEXT}, headers=h).json()
    assert j["input_retained_until"]
    with c.app.state.session_factory() as db:
        assert repo.purge_expired_inputs(db) == 0
        assert repo.purge_expired_inputs(db, now=datetime.now(UTC) + timedelta(days=2)) == 1
        assert db.execute(select(Analysis.input_text)).scalar_one() is None
    assert c.get(f"{URL}/{j['id']}", headers=h).json()["input_retained_until"] is None


def test_pipeline_crash_persists_failed_record_and_hides_internals(auth, monkeypatch):
    import app.api.routes_analyses as ra
    monkeypatch.setattr(ra, "run_pipeline", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret internal detail /etc/x")))
    c = make_client()
    r = c.post(URL, json={"job_text": SCAM_TEXT}, headers=auth)
    assert r.status_code == 500
    e = r.json()["error"]
    assert e["code"] == "analysis_failed" and "secret" not in r.text and e["analysis_id"]
    got = c.get(f"{URL}/{e['analysis_id']}", headers=auth).json()
    assert got["status"] == "failed" and got["risk_score"] is None
    assert c.get("/api/v1/dashboard/summary", headers=auth).json()["failed"] == 1


def test_unhandled_error_has_generic_body(auth, monkeypatch):
    import app.api.routes_analyses as ra
    monkeypatch.setattr(ra.repo, "list_page", lambda *a, **k: 1 / 0)
    r = make_client().get(URL, headers=auth)
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error" and "division" not in r.text


def test_ml_failure_still_returns_analysis(auth):
    c = make_client(detector=make_detector([FakePredictor(fail=True)]))
    j = c.post(URL, json={"job_text": SCAM_TEXT}, headers=auth).json()
    assert j["risk_level"] == "high" and any(p["name"] == "tfidf" and p["status"] == "failed" for p in j["detection_paths"])


# ---- URL submissions (network mocked)
def test_url_submission_private_address_rejected_without_record(client, auth):
    for u in ("http://127.0.0.1/admin", "http://169.254.169.254/latest/meta-data/", "file:///etc/passwd", "http://localhost:8000/"):
        r = post(client, auth, job_url=u)
        assert r.status_code == 422 and r.json()["error"]["code"] == "url_not_allowed", u
    assert client.get(URL, headers=auth).json()["total"] == 0


def test_url_submission_success_strips_query(auth, monkeypatch):
    import app.api.routes_analyses as ra
    from app.services.url_fetcher import FetchedPage
    monkeypatch.setattr(ra, "fetch_job_page", lambda url, s: FetchedPage(SCAM_TEXT, "https://jobs.example.com/p/1?token=SECRET", False))
    c = make_client()
    j = c.post(URL, json={"job_url": "https://jobs.example.com/p/1?token=SECRET"}, headers=auth).json()
    assert j["input_type"] == "url" and j["source_url"] == "https://jobs.example.com/p/1" and "SECRET" not in str(j)


def test_url_without_job_content_returns_unassessed_instead_of_zero_score(auth, monkeypatch):
    import app.api.routes_analyses as ra
    from app.services.url_fetcher import FetchedPage
    monkeypatch.setattr(ra, "fetch_job_page", lambda url, s: FetchedPage(
        "Example Domain. This domain is for use in documentation examples without needing permission.",
        "https://example.com/?utm_source=chatgpt.com", False))
    c = make_client()
    j = c.post(URL, json={"job_url": "https://example.com/?utm_source=chatgpt.com"}, headers=auth).json()
    assert j["status"] == "failed" and j["error_code"] == "not_job_posting"
    assert j["risk_score"] is None and j["risk_level"] is None
    assert j["source_url"] == "https://example.com/"


def test_url_network_failure_records_failed(auth, monkeypatch):
    import app.api.routes_analyses as ra
    from app.errors import AppError

    def boom(url, s):
        raise AppError(502, "url_fetch_failed", "The page could not be reached in time.")
    monkeypatch.setattr(ra, "fetch_job_page", boom)
    c = make_client()
    r = c.post(URL, json={"job_url": "https://jobs.example.com/x"}, headers=auth)
    assert r.status_code == 502 and r.json()["error"]["analysis_id"]
    assert c.get(URL, params={"status": "failed"}, headers=auth).json()["total"] == 1


# ---- uploads
def test_upload_pdf(client, auth):
    r = client.post(f"{URL}/upload", files={"file": ("offer.pdf", make_pdf(SCAM_TEXT[:90]), "application/pdf")},
                    data={"company_name": "Nexgen Solutions"}, headers=auth)
    assert r.status_code == 201, r.text
    assert r.json()["input_type"] == "file"


@pytest.mark.parametrize("name,data,status,code", [
    ("x.exe", b"MZ" * 20, 415, "unsupported_file_type"), ("x.pdf", b"nope" * 20, 415, "unsupported_file_type"),
])
def test_upload_rejections(client, auth, name, data, status, code):
    r = client.post(f"{URL}/upload", files={"file": (name, data)}, headers=auth)
    assert r.status_code == status and r.json()["error"]["code"] == code


def test_upload_too_large():
    c = make_client(make_settings(max_upload_bytes=1000))
    h = {"X-Session-Token": secrets.token_urlsafe(32)}
    r = c.post(f"{URL}/upload", files={"file": ("a.txt", b"x" * 5000)}, headers=h)
    assert r.status_code == 413 and r.json()["error"]["code"] in ("file_too_large", "payload_too_large")


def test_oversized_json_body_rejected():
    c = make_client(make_settings(max_upload_bytes=1000))
    h = {"X-Session-Token": secrets.token_urlsafe(32)}
    assert c.post(URL, content=b'{"job_text": "' + b"a" * 200_000 + b'"}', headers={**h, "content-type": "application/json"}).status_code == 413


def test_rate_limit():
    c = make_client(make_settings(rate_limit_per_minute=3))
    h = {"X-Session-Token": secrets.token_urlsafe(32)}
    codes = [c.post(URL, json={"job_text": SCAM_TEXT}, headers=h).status_code for _ in range(5)]
    assert codes[:3] == [201] * 3 and codes[3:] == [429, 429]
    assert c.get(URL, headers=h).status_code == 200      # reads are not limited


def test_cors_allows_only_configured_origin(client):
    ok = client.options(URL, headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                                      "Access-Control-Request-Headers": "x-session-token,content-type"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options(URL, headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


def test_production_rejects_wildcard_cors():
    with pytest.raises(RuntimeError):
        make_client(make_settings(environment="production", cors_origins="*"))


def test_openapi_documents_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in ("/api/v1/health", "/api/v1/analyses", "/api/v1/analyses/upload", "/api/v1/analyses/{analysis_id}", "/api/v1/dashboard/summary"):
        assert p in paths


def test_database_rate_limiter_is_shared_across_app_instances(tmp_path):
    """Two app instances on the same database share one counter (what 'memory' cannot do)."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine

    from app.db.base import Base
    from app.main import create_app
    eng = create_engine(f"sqlite:///{tmp_path/'rl.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    s = make_settings(rate_limit_per_minute=3, rate_limit_backend="database")
    a = TestClient(create_app(s, make_detector(settings=s), eng))
    b = TestClient(create_app(s, make_detector(settings=s), eng))
    h = {"X-Session-Token": secrets.token_urlsafe(32)}
    codes = [c.post(URL, json={"job_text": SCAM_TEXT}, headers=h).status_code for c in (a, b, a, b, a)]
    assert codes == [201, 201, 201, 429, 429]


def test_security_headers_present(client):
    r = client.get("/api/v1/health")
    assert r.headers["content-security-policy"].startswith("default-src 'none'")
    assert r.headers["referrer-policy"] == "no-referrer"


def test_api_returns_evidence_spans(client, auth):
    j = post(client, auth, job_text=SCAM_TEXT).json()
    fee = next(s for s in j["signals"] if s["title"] == "Registration/Training Fee")
    assert fee["evidence"][fee["evidence_start"]:fee["evidence_end"]].lower().startswith(("pay rs", "registration fee"))
