"""Orchestrates the detection stages. Each optional stage fails independently and is recorded in detection_paths."""
import logging
import time
from dataclasses import dataclass
from typing import Protocol

from . import contact as contact_mod
from . import rules as rules_mod
from . import salary as salary_mod
from .company import RegistryProvider, verify_company
from .ml import MlService
from .salary_benchmark import SalaryBenchmarkProvider
from .scoring import SCORING_VERSION, compute_score, ml_points
from .types import AnalysisInput, CompanyCheck, DetectionPath, PipelineResult, Signal

log = logging.getLogger("jobsentinel.pipeline")

LIMITATIONS = [
    "This is an automated aid, not proof that a posting or company is fraudulent or genuine.",
    "The score is a heuristic total of warning signals, not a calibrated probability.",
    "Rule patterns are English/Indian-context phrases and can miss reworded scams or flag unusual wording in real postings.",
    "The text model was trained on EMSCAD (mostly US/UK postings); it is less proven on Indian WhatsApp-style scams.",
    "A company that cannot be verified is reported as unknown, not as fraudulent.",
]


class ListingProvider(Protocol):
    def lookup(self, company_name: str, job_title: str) -> tuple[CompanyCheck, DetectionPath]: ...


@dataclass
class Detector:
    ml: MlService
    registry: RegistryProvider
    listings: ListingProvider | None = None   # informational cross-check, never scored
    salary_benchmarks: SalaryBenchmarkProvider | None = None   # real salary percentiles; the hand table is the fallback


def _recommendations(level: str, signals: list[Signal], company_status: str) -> list[str]:
    codes = {s.code for s in signals}
    recs = []
    if "rule:sensitive_data_request" in codes:
        recs.append("Do not send card photos or details, OTPs, PINs, CVVs, passwords, or premature identity/bank details to a recruiter; verify the employer independently.")
    if "rule:registration_training_fee" in codes:
        recs.append("Never pay a fee, deposit or 'kit' charge to get a job. Genuine employers do not ask for one.")
    if "contact:personal_email" in codes:
        recs.append("Find the employer's official careers page yourself (not via a link in the message) and confirm the role is listed there.")
    if "rule:suspicious_work_pattern" in codes:
        recs.append("Be cautious of tasks paid per item, daily UPI payouts, or recruiters who only use Telegram/WhatsApp.")
    if company_status in ("unknown", "registry_not_found", "unavailable", "not_provided"):
        recs.append("The company could not be confirmed here. Search independently on the official MCA portal and the employer's official website.")
    recs.append("Do not share OTPs, bank details or identity documents before a verified offer and interview process.")
    if level in ("medium", "high"):
        recs.append("If you were asked for money or sensitive data, you can report at https://cybercrime.gov.in or call 1930 (India).")
    return recs


def run_pipeline(inp: AnalysisInput, det: Detector) -> PipelineResult:
    paths: list[DetectionPath] = []
    full_text = f"{inp.job_title} {inp.company_name} {inp.text}".strip()
    signals: list[Signal] = []

    # 1. rules (required: failure propagates)
    t0 = time.perf_counter()
    rule_signals = rules_mod.detect_rule_signals(full_text)
    signals += rule_signals
    categories = {s.code for s in rule_signals if s.code != "rule:fee_no_interview_offer"}
    paths.append(DetectionPath("rules", "ok", f"{len(categories)} categories matched"))

    # 2. company verification (separate concern; failures degrade to unavailable)
    try:
        checks, company_status, cpaths, csignals = verify_company(inp.company_name, det.registry)
        paths += cpaths
        signals += csignals
    except Exception as e:  # defensive: a provider bug must not kill the analysis
        log.warning("company_stage_failed", extra={"outcome": type(e).__name__})
        checks, company_status = [], "unavailable"
        paths.append(DetectionPath(getattr(det.registry, "provider_name", "mca21"), "failed", "company lookup failed"))

    if det.listings is not None:   # informational cross-check, never scored
        try:
            lc, lp = det.listings.lookup(inp.company_name, inp.job_title)
            checks.append(lc)
            paths.append(lp)
        except Exception as e:
            log.warning("listing_stage_failed", extra={"outcome": type(e).__name__})
            paths.append(DetectionPath("adzuna", "failed", "listing check failed"))

    # 3. contact
    try:
        signals += contact_mod.analyze_contact(full_text, company_status == "known_employer", inp.company_name)
        paths.append(DetectionPath("contact", "ok"))
    except Exception as e:
        log.warning("contact_stage_failed", extra={"outcome": type(e).__name__})
        paths.append(DetectionPath("contact", "failed", "contact analysis failed"))

    # 4. salary
    try:
        sal_signals, sal_paths = salary_mod.analyze_salary_live(inp.job_title, full_text, det.salary_benchmarks)
        signals += sal_signals
        paths.append(DetectionPath("salary", "ok"))
        paths += sal_paths
    except Exception as e:
        log.warning("salary_stage_failed", extra={"outcome": type(e).__name__})
        paths.append(DetectionPath("salary", "failed", "salary analysis failed"))

    # 5. ML with fallback
    prob, pred, mlpaths = det.ml.predict(full_text)
    paths += mlpaths
    if pred is not None and prob is not None:
        pts = ml_points(prob, pred.max_points)
        sev = "high" if prob >= 0.75 else "medium" if prob >= 0.5 else "info"
        signals.append(Signal("ml:" + pred.name, "ml", f"Text model score {prob:.2f} (not a probability)", sev, pts,
                              f"Model '{pred.version}' compares wording to labelled examples of fraudulent and genuine postings. It contributes at most "
                              f"{pred.max_points} points and its score is not a calibrated probability that the posting is fraudulent."))
    score, level, breakdown = compute_score(signals)
    log.info("pipeline_done", extra={"duration_ms": int((time.perf_counter() - t0) * 1000), "outcome": level})

    return PipelineResult(
        risk_score=score, risk_level=level, signals=signals, company_checks=checks, company_status=company_status,
        detection_paths=paths, score_breakdown=breakdown,
        versions={"rules": rules_mod.RULES_VERSION, "scoring": SCORING_VERSION, "model": pred.version if pred else None},
        ml_probability=prob, ml_model=pred.name if pred else None,
        recommendations=_recommendations(level, signals, company_status), limitations=LIMITATIONS)
