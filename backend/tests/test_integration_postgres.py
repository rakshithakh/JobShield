"""End-to-end flow on a real PostgreSQL: Alembic migration -> API -> detection (real TF-IDF artifacts) -> DB -> response.
Skipped unless TEST_POSTGRES_URL is set, e.g. postgresql+psycopg://jobsentinel:testpw@localhost:5432/jobsentinel_test"""
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app.main import create_app
from app.services.company import Mca21Provider
from app.services.ml import MlService
from app.services.pipeline import Detector
from tests.conftest import REAL_TEXT, SCAM_TEXT, make_settings

PG = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not PG, reason="TEST_POSTGRES_URL not set")
BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def pg_client():
    from fastapi.testclient import TestClient
    env = {**os.environ, "DATABASE_URL": PG}
    eng = create_engine(PG)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True)
    s = make_settings(database_url=PG)
    det = Detector(ml=MlService.from_settings(s), registry=Mca21Provider(s))   # REAL model artifacts
    yield TestClient(create_app(s, det, eng))
    eng.dispose()


def test_migration_created_schema_and_indexes(pg_client):
    insp = inspect(create_engine(PG))
    assert {"analyses", "analysis_signals", "company_checks", "alembic_version"} <= set(insp.get_table_names())
    idx = {i["name"] for i in insp.get_indexes("analyses")}
    assert {"ix_analyses_owner_created", "ix_analyses_owner_level"} <= idx
    assert insp.get_foreign_keys("analysis_signals")[0]["options"].get("ondelete") == "CASCADE"
    cols = {c["name"]: str(c["type"]) for c in insp.get_columns("analyses")}
    assert cols["detection_paths"] == "JSONB" and "TIMESTAMP" in cols["created_at"]


def test_full_flow_with_real_model(pg_client):
    h = {"X-Session-Token": secrets.token_urlsafe(32)}
    r = pg_client.post("/api/v1/analyses", json={"job_text": SCAM_TEXT, "company_name": "Nexgen Solutions", "job_title": "Data Entry"}, headers=h)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["risk_level"] == "high" and j["versions"]["model"].startswith("tfidf-lr:")
    assert any(p["name"] == "tfidf" and p["status"] == "ok" for p in j["detection_paths"])
    got = pg_client.get(f"/api/v1/analyses/{j['id']}", headers=h).json()
    assert got["signals"] == j["signals"] and got["created_at"].endswith(("Z", "+00:00"))
    real = pg_client.post("/api/v1/analyses", json={"job_text": REAL_TEXT, "company_name": "Infosys"}, headers=h).json()
    assert real["risk_level"] == "low"
    assert pg_client.get("/api/v1/analyses", params={"q": "nexgen"}, headers=h).json()["total"] == 1
    s = pg_client.get("/api/v1/dashboard/summary", headers=h).json()
    assert s["total_analyses"] == 2 and s["risk_distribution"] == {"low": 1, "medium": 0, "high": 1}
    other = {"X-Session-Token": secrets.token_urlsafe(32)}
    assert pg_client.get(f"/api/v1/analyses/{j['id']}", headers=other).status_code == 404
    assert pg_client.delete(f"/api/v1/analyses/{j['id']}", headers=h).status_code == 204
    with create_engine(PG).connect() as c:
        assert c.execute(text("select count(*) from analysis_signals where analysis_id = :i"), {"i": j["id"]}).scalar() == 0


def test_health_on_postgres(pg_client):
    assert pg_client.get("/api/v1/health").json()["database"] == "ok"


def test_database_rate_limiter_is_atomic_across_threads_on_postgres(pg_client):
    """Concurrent requests must not exceed the limit: the upsert increments atomically in PostgreSQL."""
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy.orm import sessionmaker

    from app.ratelimit import DatabaseRateLimiter
    eng = create_engine(PG)
    rl = DatabaseRateLimiter(sessionmaker(bind=eng), 10)
    with ThreadPoolExecutor(8) as ex:
        allowed = sum(ok for ok, _ in ex.map(lambda _: rl.check("203.0.113.9"), range(40)))
    assert allowed == 10
