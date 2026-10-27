import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # SHA-256 of the anonymous X-Session-Token. Scopes every query; it is NOT a login.
    owner_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))          # completed | failed
    error_code: Mapped[str | None] = mapped_column(String(64))

    input_type: Mapped[str] = mapped_column(String(8))       # text | url | file
    job_title: Mapped[str | None] = mapped_column(String(200))
    company_name: Mapped[str | None] = mapped_column(String(200), index=True)
    source_url: Mapped[str | None] = mapped_column(String(2048))   # query string stripped
    input_sha256: Mapped[str | None] = mapped_column(String(64))
    input_length: Mapped[int | None] = mapped_column(Integer)
    input_truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    input_text: Mapped[str | None] = mapped_column(Text)            # only if INPUT_TEXT_RETENTION_DAYS > 0
    input_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    risk_score: Mapped[int | None] = mapped_column(Integer)
    risk_level: Mapped[str | None] = mapped_column(String(8))       # low | medium | high
    company_status: Mapped[str | None] = mapped_column(String(32))
    ml_probability: Mapped[float | None] = mapped_column(Float)
    ml_model: Mapped[str | None] = mapped_column(String(32))
    rules_version: Mapped[str | None] = mapped_column(String(32))
    scoring_version: Mapped[str | None] = mapped_column(String(32))
    model_version: Mapped[str | None] = mapped_column(String(64))
    score_breakdown: Mapped[dict | None] = mapped_column(JsonType)
    detection_paths: Mapped[list | None] = mapped_column(JsonType)
    recommendations: Mapped[list | None] = mapped_column(JsonType)
    processing_ms: Mapped[int | None] = mapped_column(Integer)

    signals: Mapped[list["AnalysisSignal"]] = relationship(back_populates="analysis", cascade="all, delete-orphan",
                                                           order_by="AnalysisSignal.position")
    company_checks: Mapped[list["CompanyCheckRow"]] = relationship(back_populates="analysis", cascade="all, delete-orphan",
                                                                    order_by="CompanyCheckRow.id")

    __table_args__ = (
        Index("ix_analyses_owner_created", "owner_hash", "created_at"),
        Index("ix_analyses_owner_level", "owner_hash", "risk_level"),
    )


class AnalysisSignal(Base):
    __tablename__ = "analysis_signals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(8))
    points: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(String(300))
    evidence_start: Mapped[int | None] = mapped_column(Integer)
    evidence_end: Mapped[int | None] = mapped_column(Integer)
    analysis: Mapped[Analysis] = relationship(back_populates="signals")


class CompanyCheckRow(Base):
    __tablename__ = "company_checks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    analysis: Mapped[Analysis] = relationship(back_populates="company_checks")


class RateLimitBucket(Base):
    """Fixed-window counters for the shared rate limiter. `key` is a hash of the client IP (no raw IPs stored)."""
    __tablename__ = "rate_limit_buckets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window: Mapped[int] = mapped_column(Integer, primary_key=True)   # unix minute
    count: Mapped[int] = mapped_column(Integer, default=0)
