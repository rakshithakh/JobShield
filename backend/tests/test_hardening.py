import json
import secrets
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import make_session_factory
from app.ratelimit import DatabaseRateLimiter
from app.services.scoring import SCORING_VERSION
from tests.conftest import SCAM_TEXT, make_client, make_settings

ART = Path(__file__).resolve().parent.parent / "ml" / "artifacts"


def sqlite_factory():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return make_session_factory(eng)


def test_database_rate_limiter_counts_and_resets_per_window(monkeypatch):
    rl = DatabaseRateLimiter(sqlite_factory(), 3)
    assert [rl.check("1.2.3.4")[0] for _ in range(5)] == [True, True, True, False, False]
    assert rl.check("5.6.7.8")[0] is True                       # other clients unaffected
    import app.ratelimit as m
    real = m.time.time
    monkeypatch.setattr(m.time, "time", lambda: real() + 61)   # next window
    assert rl.check("1.2.3.4")[0] is True


def test_two_app_instances_share_one_database_limit():
    """Memory limiter: each instance has its own budget. Database limiter: one shared budget."""
    sf = sqlite_factory()
    a, b = DatabaseRateLimiter(sf, 2), DatabaseRateLimiter(sf, 2)
    assert [a.check("ip")[0], b.check("ip")[0], a.check("ip")[0], b.check("ip")[0]] == [True, True, False, False]


def test_database_backend_is_wired_through_the_api():
    c = make_client(make_settings(rate_limit_backend="database", rate_limit_per_minute=2))
    h = {"X-Session-Token": secrets.token_urlsafe(32)}
    codes = [c.post("/api/v1/analyses", json={"job_text": SCAM_TEXT}, headers=h).status_code for _ in range(3)]
    assert codes == [201, 201, 429]


def test_security_headers_on_api_but_docs_stay_usable(client):
    h = client.get("/api/v1/health").headers
    assert h["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert h["x-frame-options"] == "DENY" and h["cache-control"] == "no-store"
    assert "content-security-policy" not in client.get("/docs").headers      # Swagger UI needs its CDN assets
    assert "strict-transport-security" not in h                                # development


def test_hsts_in_production():
    c = make_client(make_settings(environment="production", cors_origins="https://app.example"))
    assert "max-age=" in c.get("/api/v1/health").headers["strict-transport-security"]


# ---- ML data hygiene and shipped-artifact consistency
def test_dedupe_and_split_have_no_leakage(tmp_path):
    from ml.common import load_dataset, split
    rows = []
    for i in range(200):
        rows.append({"title": f"Job {i}", "description": f"unique description number {i} " * 3, "fraudulent": int(i % 10 == 0)})
    rows += [dict(rows[0]), dict(rows[1]), dict(rows[10])]        # exact duplicates
    p = tmp_path / "d.csv"; pd.DataFrame(rows).to_csv(p, index=False)
    df = load_dataset(str(p))
    assert len(df) == 200
    tr, va, te, tv = split(df)
    keys = lambda d: set(d["title"] + "|" + d["description"])
    assert not (keys(tr) & keys(te)) and not (keys(va) & keys(te)) and not (keys(tr) & keys(va))
    assert len(tr) + len(va) + len(te) == 200
    assert abs(te["fraudulent"].mean() - df["fraudulent"].mean()) < 0.03       # stratified


def test_shipped_evaluation_matches_current_code_and_artifacts():
    """Fails if scoring or the model changes without re-running `python -m ml.evaluate` (stale README numbers)."""
    ev = json.loads((ART / "evaluation.json").read_text())
    meta = json.loads((ART / "model_metadata.json").read_text())
    from app.services.rules import RULES_VERSION
    assert ev["scoring_version"] == SCORING_VERSION and ev["rules_version"] == RULES_VERSION
    assert ev["data_provenance"]["training_data_hash_matches_evaluation"] == (
        ev["dataset_sha256"] == meta["dataset"]["sha256"]
    )
    if ev["dataset_sha256"] != meta["dataset"]["sha256"]:
        assert any("independence from training data is not verified" in caveat for caveat in ev["caveats"])
    assert meta["dataset"]["name"].startswith("EMSCAD")
    assert ev["levels"]["medium_or_high (>=35)"]["precision"] > 0.8


def test_env_example_documents_only_real_settings_and_all_of_them():
    import re

    from app.config import Settings
    fields = {f.upper() for f in Settings.model_fields}
    doc = set(re.findall(r"^#?\s*([A-Z_]+)=", (Path(__file__).resolve().parent.parent / ".env.example").read_text(), re.M))
    assert doc <= fields, f"documented but not a setting: {doc - fields}"
    assert fields <= doc, f"setting missing from .env.example: {fields - doc}"
