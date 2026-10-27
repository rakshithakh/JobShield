from typing import Literal

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import repository as repo
from ..schemas import AnalysisSummary, DashboardSummary, DetectionPathOut, HealthOut
from ..services.pipeline import Detector
from ..services.rules import RULES_VERSION
from ..services.scoring import SCORING_VERSION
from .deps import get_db, get_detector, get_owner, get_settings_dep

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthOut, tags=["health"])
def health(request: Request, det: Detector = Depends(get_detector), settings=Depends(get_settings_dep)):
    try:
        with request.app.state.engine.connect() as c:
            c.execute(text("SELECT 1"))
        db: Literal["ok", "unavailable"] = "ok"
    except Exception:
        db = "unavailable"
    paths = [p.__dict__ for p in det.ml.load_paths]
    paths.append({"name": "company_search", "status": "not_configured",
                  "detail": "online company search is disabled; verify employers on official sources"})
    paths.append({"name": "adzuna", "status": "ok" if settings.adzuna_app_id and settings.adzuna_app_key else "not_configured",
                  "detail": "keys configured (live lookup not verified at startup)" if settings.adzuna_app_id and settings.adzuna_app_key else "ADZUNA_* not set"})
    model = next((p.version for p in det.ml.predictors), None)
    return HealthOut(status="ok" if db == "ok" else "degraded", database=db, detection_paths=[DetectionPathOut(**p) for p in paths],
                     versions={"rules": RULES_VERSION, "scoring": SCORING_VERSION, "model": model})


@router.get("/dashboard/summary", response_model=DashboardSummary, tags=["dashboard"])
def dashboard_summary(db: Session = Depends(get_db), owner: str = Depends(get_owner)):
    s = repo.dashboard_summary(db, owner)
    s["recent"] = [AnalysisSummary.model_validate(a) for a in s["recent"]]
    return s
