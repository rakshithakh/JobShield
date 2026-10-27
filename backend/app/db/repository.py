"""All database access. Every read/write is scoped by owner_hash; queries are parameterised via SQLAlchemy."""
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, selectinload

from ..services.types import PipelineResult
from .models import Analysis, AnalysisSignal, CompanyCheckRow, utcnow


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def create_completed(db: Session, *, owner_hash: str, input_type: str, job_title: str, company_name: str,
                     source_url: str | None, text: str, truncated: bool, result: PipelineResult,
                     processing_ms: int, retention_days: int) -> Analysis:
    now = utcnow()
    a = Analysis(
        owner_hash=owner_hash, status="completed", created_at=now, completed_at=now, input_type=input_type,
        job_title=job_title or None, company_name=company_name or None, source_url=source_url,
        input_sha256=hashlib.sha256(text.encode()).hexdigest(), input_length=len(text), input_truncated=truncated,
        input_text=text if retention_days > 0 else None,
        input_expires_at=(now + timedelta(days=retention_days)) if retention_days > 0 else None,
        risk_score=result.risk_score, risk_level=result.risk_level, company_status=result.company_status,
        ml_probability=result.ml_probability, ml_model=result.ml_model,
        rules_version=result.versions["rules"], scoring_version=result.versions["scoring"], model_version=result.versions["model"],
        score_breakdown=result.score_breakdown, detection_paths=[p.__dict__ for p in result.detection_paths],
        recommendations=result.recommendations, processing_ms=processing_ms)
    a.signals = [AnalysisSignal(position=i, code=s.code, source=s.source, title=s.title, severity=s.severity,
                                points=s.points, explanation=s.explanation, evidence=(s.evidence or None) and s.evidence[:300],
                                evidence_start=s.evidence_span[0] if s.evidence_span else None,
                                evidence_end=s.evidence_span[1] if s.evidence_span else None)
                 for i, s in enumerate(result.signals)]
    a.company_checks = [CompanyCheckRow(provider=c.provider, status=c.status, summary=c.summary, source_url=c.source_url,
                                        latency_ms=c.latency_ms, checked_at=now) for c in result.company_checks]
    db.add(a)
    db.commit()
    return a


def create_failed(db: Session, *, owner_hash: str, input_type: str, job_title: str, company_name: str,
                  source_url: str | None, error_code: str) -> Analysis:
    a = Analysis(owner_hash=owner_hash, status="failed", error_code=error_code, input_type=input_type,
                 job_title=job_title or None, company_name=company_name or None, source_url=source_url)
    db.add(a)
    db.commit()
    return a


def get_one(db: Session, owner_hash: str, analysis_id: uuid.UUID) -> Analysis | None:
    stmt = (select(Analysis).where(Analysis.id == analysis_id, Analysis.owner_hash == owner_hash)
            .options(selectinload(Analysis.signals), selectinload(Analysis.company_checks)))
    return db.execute(stmt).scalar_one_or_none()


def delete_one(db: Session, owner_hash: str, analysis_id: uuid.UUID) -> bool:
    a = db.execute(select(Analysis).where(Analysis.id == analysis_id, Analysis.owner_hash == owner_hash)).scalar_one_or_none()
    if not a:
        return False
    db.delete(a)
    db.commit()
    return True


def list_page(db: Session, owner_hash: str, *, page: int, page_size: int, risk_level: str | None,
              status: str | None, q: str | None, sort: str) -> tuple[list[Analysis], int]:
    cond = [Analysis.owner_hash == owner_hash]
    if risk_level:
        cond.append(Analysis.risk_level == risk_level)
    if status:
        cond.append(Analysis.status == status)
    if q:
        like = f"%{_escape_like(q.strip().lower())}%"
        cond.append(or_(func.lower(Analysis.company_name).like(like, escape="\\"),
                        func.lower(Analysis.job_title).like(like, escape="\\")))
    total = db.execute(select(func.count()).select_from(Analysis).where(*cond)).scalar_one()
    order: Any = {"newest": Analysis.created_at.desc(), "oldest": Analysis.created_at.asc(),
             "risk_desc": Analysis.risk_score.desc().nulls_last(), "risk_asc": Analysis.risk_score.asc().nulls_last()}[sort]
    rows = db.execute(select(Analysis).where(*cond).order_by(order, Analysis.id).limit(page_size).offset((page - 1) * page_size)).scalars().all()
    return list(rows), total


def dashboard_summary(db: Session, owner_hash: str, recent_limit: int = 5) -> dict:
    base = Analysis.owner_hash == owner_hash
    total = db.execute(select(func.count()).select_from(Analysis).where(base)).scalar_one()
    failed = db.execute(select(func.count()).select_from(Analysis).where(base, Analysis.status == "failed")).scalar_one()
    dist_rows = db.execute(select(Analysis.risk_level, func.count()).where(base, Analysis.status == "completed")
                           .group_by(Analysis.risk_level)).all()
    dist = {"low": 0, "medium": 0, "high": 0}
    dist.update({lvl: n for lvl, n in dist_rows if lvl})
    avg = db.execute(select(func.avg(Analysis.risk_score)).where(base, Analysis.status == "completed")).scalar_one()
    recent = db.execute(select(Analysis).where(base).order_by(Analysis.created_at.desc()).limit(recent_limit)).scalars().all()
    return {"total_analyses": total, "completed": total - failed, "failed": failed, "risk_distribution": dist,
            "average_risk_score": round(float(avg), 1) if avg is not None else None, "recent": list(recent)}


def purge_expired_inputs(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    res = db.execute(update(Analysis).where(Analysis.input_text.is_not(None), Analysis.input_expires_at <= now)
                     .values(input_text=None))
    db.commit()
    return cast(CursorResult, res).rowcount or 0
