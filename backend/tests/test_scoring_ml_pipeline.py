import shutil
from pathlib import Path

import pytest

from app.services.ml import MlService, MlUnavailable, TfidfPredictor
from app.services.pipeline import run_pipeline
from app.services.scoring import compute_score, level_for, ml_points
from app.services.types import AnalysisInput, Signal
from tests.conftest import REAL_TEXT, SCAM_TEXT, FakePredictor, make_detector, make_settings

ARTIFACTS = Path(__file__).resolve().parent.parent / "ml" / "artifacts"


def test_ml_points_formula():
    assert ml_points(0.1, 40) == 0 and ml_points(0.2, 40) == 0
    assert ml_points(0.55, 40) == 20 and ml_points(0.9, 40) == 40 and ml_points(1.0, 40) == 40 and ml_points(None, 40) == 0


def test_levels_thresholds():
    assert (level_for(34), level_for(35), level_for(59), level_for(60)) == ("low", "medium", "medium", "high")


def test_score_caps_rules_and_total():
    sigs = [Signal(f"r{i}", "rules", "x", "high", 30, "") for i in range(4)] + [Signal("c", "contact", "x", "high", 25, ""),
                                                                                  Signal("s", "salary", "x", "high", 30, "")]
    score, level, b = compute_score(sigs)
    assert b["rules"] == 70 and b["raw_total"] == 125 and score == 100 and level == "high"


def test_nothing_subtracts_from_score():
    score, _, _ = compute_score([Signal("a", "contact", "x", "info", 0, ""), Signal("b", "salary", "x", "info", 0, "")])
    assert score == 0


def test_pipeline_scam_is_high_and_has_evidence():
    r = run_pipeline(AnalysisInput(SCAM_TEXT, "Nexgen Solutions", "Data Entry Operator"), make_detector([FakePredictor(0.74)]))
    assert r.risk_level == "high" and r.risk_score >= 60
    assert all(s.evidence for s in r.signals if s.source == "rules")
    assert r.score_breakdown["rules"] <= 70
    assert r.versions["model"] == "fake:1"


def test_pipeline_real_posting_scores_low_and_not_called_safe():
    r = run_pipeline(AnalysisInput(REAL_TEXT, "Infosys", "Software Engineer"), make_detector([FakePredictor(0.3)]))
    assert r.risk_level == "low" and r.risk_score <= 5
    assert any("not proof" in l for l in r.limitations)


def test_impersonation_of_known_employer_is_flagged():
    r = run_pipeline(AnalysisInput("Infosys hiring freshers. CTC 4 LPA. Send resume to infosys.hr.recruit@gmail.com", "Infosys", ""),
                     make_detector([FakePredictor(0.3)]))
    contact = next(s for s in r.signals if s.code == "contact:personal_email")
    assert contact.severity == "high" and contact.points == 25 and r.risk_level == "low"


def test_negated_fee_real_posting_not_penalised():
    t = "Accountant, Tally, 4 LPA. We never ask for a registration fee or security deposit. Apply: careers@acmewidgets.in"
    r = run_pipeline(AnalysisInput(t, "Acme Widgets Pvt Ltd", "Accountant"), make_detector([FakePredictor(0.3)]))
    assert r.risk_score <= 5 and r.company_status == "unknown"


def test_sensitive_data_messaging_rule_includes_specific_safety_advice():
    text = ("No technical interview required. Guaranteed job offer within 24 hours. "
            "Send Aadhaar card, PAN card and bank account details over WhatsApp for immediate onboarding.")
    r = run_pipeline(AnalysisInput(text), make_detector([FakePredictor(0.1)]))
    assert "rule:sensitive_data_messaging" in {s.code for s in r.signals}
    assert any("Do not send Aadhaar, PAN, bank details" in tip for tip in r.recommendations)


def test_otp_request_and_cancellation_ultimatum_reach_high_risk():
    text = ("Your job offer is approved. To release your joining bonus, send your Aadhaar number, "
            "PAN card, bank account number and OTP through WhatsApp. "
            "Complete verification within 30 minutes or your offer will be cancelled.")
    r = run_pipeline(AnalysisInput(text), make_detector([FakePredictor(0.35)]))
    codes = {s.code for s in r.signals}
    assert "rule:sensitive_data_messaging" in codes
    assert "rule:urgency_tactics" in codes
    assert r.risk_level == "high" and r.risk_score >= 60


def test_upi_deposit_for_confirmed_no_interview_placement_reaches_high_risk():
    text = ("Your placement is confirmed. Pay a refundable security deposit of ₹5,000 by UPI. "
            "The company guarantees employment after payment. No interview or technical round will be conducted.")
    r = run_pipeline(AnalysisInput(text), make_detector([FakePredictor(0.1)]))
    assert "rule:fee_no_interview_offer" in {s.code for s in r.signals}
    assert r.risk_level == "high" and r.risk_score >= 60


def test_gmail_contact_mentioned_without_address_adds_only_weak_points():
    r = run_pipeline(AnalysisInput("Send your portfolio to our company Gmail address."),
                     make_detector([FakePredictor(0.1)]))
    assert "contact:free_email_mentioned" in {s.code for s in r.signals}
    assert r.risk_score == 10 and r.risk_level == "low"


def test_ml_failure_falls_back_and_is_recorded():
    det = make_detector([FakePredictor(fail=True), FakePredictor(0.9)])
    r = run_pipeline(AnalysisInput(SCAM_TEXT), det)
    statuses = [(p.name, p.status) for p in r.detection_paths if p.name == "tfidf"]
    assert ("tfidf", "failed") in statuses and ("tfidf", "ok") in statuses
    assert r.ml_probability == 0.9


def test_all_ml_unavailable_still_scores_from_rules():
    det = make_detector([])
    r = run_pipeline(AnalysisInput(SCAM_TEXT), det)
    assert r.ml_probability is None and r.risk_level == "high"
    assert any(p.name == "distilbert" and p.status == "not_configured" for p in r.detection_paths)


def test_stage_failure_is_recorded_not_fatal(monkeypatch):
    import app.services.salary as sal
    monkeypatch.setattr(sal, "analyze_salary", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    r = run_pipeline(AnalysisInput(SCAM_TEXT), make_detector())
    assert any(p.name == "salary" and p.status == "failed" for p in r.detection_paths)


# ---- real TF-IDF artifacts
def test_real_artifacts_load_and_predict():
    p = TfidfPredictor(str(ARTIFACTS))
    assert 0.0 <= p.predict(SCAM_TEXT) <= 1.0
    assert p.predict(SCAM_TEXT) > p.predict("Backend engineer, Python and Django, 3 years experience, Pune office.")
    assert p.version.startswith("tfidf-lr:")


def test_tampered_artifact_is_refused(tmp_path):
    for f in ARTIFACTS.iterdir():
        shutil.copy(f, tmp_path / f.name)
    (tmp_path / "scam_model.pkl").write_bytes(b"malicious")
    with pytest.raises(MlUnavailable):
        TfidfPredictor(str(tmp_path))


def test_missing_artifacts_reported_unavailable(tmp_path):
    svc = MlService.from_settings(make_settings(model_artifact_dir=str(tmp_path)))
    assert svc.predictors == [] and any(p.name == "tfidf" and p.status == "unavailable" for p in svc.load_paths)


def test_distilbert_missing_deps_or_weights_degrades(tmp_path):
    svc = MlService.from_settings(make_settings(model_artifact_dir=str(ARTIFACTS), distilbert_model_dir=str(tmp_path)))
    assert any(p.name == "distilbert" and p.status == "unavailable" for p in svc.load_paths)
    assert [p.name for p in svc.predictors] == ["tfidf"]
