import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import get_settings

RiskLevel = Literal["low", "medium", "high"]


class AnalysisCreate(BaseModel):
    job_title: str | None = Field(default=None, max_length=200)
    company_name: str | None = Field(default=None, max_length=200)
    job_text: str | None = None
    job_url: str | None = Field(default=None, max_length=2048)

    @field_validator("job_title", "company_name", "job_text", "job_url", mode="before")
    @classmethod
    def _strip(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @model_validator(mode="after")
    def _one_source(self):
        if bool(self.job_text) == bool(self.job_url):
            raise ValueError("Provide either job_text or job_url (exactly one).")
        if self.job_text:
            mx = get_settings().max_text_chars
            if len(self.job_text) < 20:
                raise ValueError("job_text must be at least 20 characters.")
            if len(self.job_text) > mx:
                raise ValueError(f"job_text must be at most {mx} characters.")
        return self


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    source: str
    title: str
    severity: str
    points: int
    explanation: str
    evidence: str | None = None
    evidence_start: int | None = None
    evidence_end: int | None = None


class CompanyCheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    provider: str
    status: str
    summary: str
    source_url: str | None = None
    latency_ms: int | None = None
    checked_at: datetime | None = None


class DetectionPathOut(BaseModel):
    name: str
    status: str
    detail: str = ""


class AnalysisSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    status: str
    error_code: str | None = None
    input_type: str
    job_title: str | None = None
    company_name: str | None = None
    risk_score: int | None = None
    risk_level: RiskLevel | None = None
    company_status: str | None = None


class AnalysisDetail(AnalysisSummary):
    source_url: str | None = None
    input_length: int | None = None
    input_truncated: bool = False
    input_retained_until: datetime | None = None
    ml_probability: float | None = None
    ml_model: str | None = None
    versions: dict = {}
    score_breakdown: dict = {}
    signals: list[SignalOut] = []
    company_checks: list[CompanyCheckOut] = []
    detection_paths: list[DetectionPathOut] = []
    recommendations: list[str] = []
    limitations: list[str] = []
    processing_ms: int | None = None


class Page(BaseModel):
    items: list[AnalysisSummary]
    page: int
    page_size: int
    total: int
    total_pages: int


class DashboardSummary(BaseModel):
    total_analyses: int
    completed: int
    failed: int
    risk_distribution: dict[str, int]
    average_risk_score: float | None
    recent: list[AnalysisSummary]


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    detection_paths: list[DetectionPathOut]
    versions: dict
