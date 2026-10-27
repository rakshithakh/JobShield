from typing import Any, cast

from ..db.models import Analysis
from ..schemas import AnalysisDetail, CompanyCheckOut, DetectionPathOut, SignalOut
from ..services.pipeline import LIMITATIONS


def to_detail(a: Analysis) -> AnalysisDetail:
    """Explicit mapping so nullable JSON columns (failed analyses) become empty defaults."""
    return AnalysisDetail(
        id=a.id, created_at=a.created_at, status=a.status, input_type=a.input_type, job_title=a.job_title,
        company_name=a.company_name, risk_score=a.risk_score, risk_level=cast(Any, a.risk_level), company_status=a.company_status,
        error_code=a.error_code, source_url=a.source_url, input_length=a.input_length, input_truncated=bool(a.input_truncated),
        input_retained_until=a.input_expires_at if a.input_text else None,
        ml_probability=a.ml_probability, ml_model=a.ml_model,
        versions={"rules": a.rules_version, "scoring": a.scoring_version, "model": a.model_version},
        score_breakdown=a.score_breakdown or {},
        signals=[SignalOut.model_validate(s) for s in a.signals],
        company_checks=[CompanyCheckOut.model_validate(c) for c in a.company_checks],
        detection_paths=[DetectionPathOut(**p) for p in (a.detection_paths or [])],
        recommendations=a.recommendations or [],
        limitations=LIMITATIONS if a.status == "completed" else [],
        processing_ms=a.processing_ms)
