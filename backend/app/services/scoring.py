"""Risk score (scoring-4).  A heuristic 0-100 *warning-signal total*, NOT a calibrated probability of fraud.

    rules      = min(sum(points of matched rule categories), 70)
    ml         = round(clip((p - 0.2) / 0.7, 0, 1) * model.max_points)  # p = model score; full 40 points (TF-IDF) at p >= 0.9
    contact    = personal email 25 once; known-employer context raises severity but adds no duplicate points
    salary     = 30 / 15 / 8 for far-above / above / far-below the rough benchmark range, else 0
    company    = 15 name heuristic, 35 registry says struck off / dissolved (unknown or unverifiable adds 0)
    score      = min(100, rules + ml + contact + salary + company)

The TF-IDF model is worth up to 40 points because on a held-out EMSCAD test set it flagged postings with 0.90-0.96
precision at p >= 0.5-0.9 (see ml/artifacts/model_metadata.json). By itself it can reach "medium" (>= 35) but not "high":
"high" needs corroborating signals. Its score is not a calibrated probability.
Only warning evidence adds points; nothing subtracts. A low score therefore means "few warning signals were found",
not "this job is safe". Each signal category is counted once (no double counting between rules and contact).
Levels: >= 60 high, >= 35 medium, otherwise low  (thresholds carried over from the original app).
"""
from .types import Signal

SCORING_VERSION = "scoring-4"
HIGH, MEDIUM = 60, 35


ML_RAMP_LOW, ML_RAMP_HIGH = 0.2, 0.9   # chosen on the validation split (ranking AUC 0.89 -> 0.93), not on test


def ml_points(prob: float | None, max_points: int) -> int:
    if prob is None:
        return 0
    return round(min(1.0, max(0.0, (prob - ML_RAMP_LOW) / (ML_RAMP_HIGH - ML_RAMP_LOW))) * max_points)


def level_for(score: int) -> str:
    return "high" if score >= HIGH else "medium" if score >= MEDIUM else "low"


def compute_score(signals: list[Signal]) -> tuple[int, str, dict]:
    from .rules import RULE_POINTS_CAP
    by: dict[str, int] = {}
    for s in signals:
        by[s.source] = by.get(s.source, 0) + s.points
    breakdown = {
        "rules": min(by.get("rules", 0), RULE_POINTS_CAP),
        "ml": by.get("ml", 0),
        "contact": by.get("contact", 0),
        "salary": by.get("salary", 0),
        "company": by.get("company", 0),
    }
    raw = sum(breakdown.values())
    score = min(100, raw)
    breakdown.update({"raw_total": raw, "capped_total": score})
    return score, level_for(score), breakdown
