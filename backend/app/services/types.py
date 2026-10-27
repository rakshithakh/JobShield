"""Plain data containers passed between pipeline stages (no framework dependencies)."""
from dataclasses import dataclass, field

SEVERITIES = ("info", "low", "medium", "high")


@dataclass
class Signal:
    code: str
    source: str          # rules | contact | salary | company | ml
    title: str
    severity: str        # info | low | medium | high
    points: int
    explanation: str
    evidence: str | None = None
    evidence_span: tuple[int, int] | None = None   # (start, end) of the matched phrase inside `evidence`


@dataclass
class CompanyCheck:
    provider: str        # trusted_list | name_heuristic | company_search | mca21 (legacy)
    status: str          # see company.py for the status vocabulary
    summary: str
    source_url: str | None = None
    latency_ms: int | None = None


@dataclass
class DetectionPath:
    name: str            # rules | contact | salary | tfidf | distilbert | company_search
    status: str          # ok | unavailable | not_configured | failed | skipped
    detail: str = ""


@dataclass
class AnalysisInput:
    text: str
    company_name: str = ""
    job_title: str = ""


@dataclass
class PipelineResult:
    risk_score: int
    risk_level: str
    signals: list[Signal]
    company_checks: list[CompanyCheck]
    company_status: str
    detection_paths: list[DetectionPath]
    score_breakdown: dict
    versions: dict
    ml_probability: float | None
    ml_model: str | None
    recommendations: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
