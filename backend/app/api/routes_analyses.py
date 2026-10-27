import logging
import math
import time
import uuid
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import repository as repo
from ..errors import AppError
from ..schemas import AnalysisCreate, AnalysisDetail, AnalysisSummary, Page
from ..services.extraction import extract_text
from ..services.job_relevance import looks_like_job_posting
from ..services.pipeline import Detector, run_pipeline
from ..services.types import AnalysisInput
from ..services.url_fetcher import fetch_job_page
from .deps import get_db, get_detector, get_owner, get_settings_dep, rate_limit
from .serializers import to_detail

log = logging.getLogger("jobsentinel.analyses")
router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"])


def _clean_url(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.hostname}{p.path}"[:2048]


def _analyse(db: Session, owner: str, settings: Settings, det: Detector, *, input_type: str, title: str, company: str,
             text: str, source_url: str | None, truncated: bool) -> AnalysisDetail:
    t0 = time.perf_counter()
    try:
        result = run_pipeline(AnalysisInput(text=text, company_name=company, job_title=title), det)
    except Exception as e:
        log.error("pipeline_failed", extra={"outcome": type(e).__name__})
        failed = repo.create_failed(db, owner_hash=owner, input_type=input_type, job_title=title, company_name=company,
                                    source_url=source_url, error_code="pipeline_error")
        raise AppError(500, "analysis_failed", "The analysis could not be completed. It was recorded as failed.", str(failed.id)) from e
    ms = int((time.perf_counter() - t0) * 1000)
    a = repo.create_completed(db, owner_hash=owner, input_type=input_type, job_title=title, company_name=company,
                              source_url=source_url, text=text, truncated=truncated, result=result, processing_ms=ms,
                              retention_days=settings.input_text_retention_days)
    log.info("analysis_completed", extra={"analysis_id": str(a.id), "duration_ms": ms, "outcome": result.risk_level})
    saved = repo.get_one(db, owner, a.id)
    if saved is None:  # pragma: no cover - row was just committed
        raise AppError(500, "internal_error", "Something went wrong on our side.")
    return to_detail(saved)


@router.post("", response_model=AnalysisDetail, status_code=201, dependencies=[Depends(rate_limit)])
def create_analysis(body: AnalysisCreate, db: Session = Depends(get_db), owner: str = Depends(get_owner),
                    settings: Settings = Depends(get_settings_dep), det: Detector = Depends(get_detector)):
    title, company = body.job_title or "", body.company_name or ""
    if body.job_text:
        return _analyse(db, owner, settings, det, input_type="text", title=title, company=company, text=body.job_text,
                        source_url=None, truncated=False)
    url = body.job_url
    if url is None:  # unreachable: the schema requires exactly one of text/url
        raise AppError(422, "validation_error", "Provide job_text or job_url.")
    try:
        page = fetch_job_page(url, settings)
    except AppError as e:
        if e.status_code >= 500 or e.status_code == 502:  # remote/network failure: keep a failed record for history
            failed = repo.create_failed(db, owner_hash=owner, input_type="url", job_title=title, company_name=company,
                                        source_url=_clean_url(url), error_code=e.code)
            e.analysis_id = str(failed.id)
        raise
    if not looks_like_job_posting(page.text):
        unassessed = repo.create_failed(db, owner_hash=owner, input_type="url", job_title=title, company_name=company,
                                        source_url=_clean_url(page.final_url), error_code="not_job_posting")
        log.info("analysis_not_assessed", extra={"analysis_id": str(unassessed.id), "outcome": "not_job_posting"})
        return to_detail(unassessed)
    return _analyse(db, owner, settings, det, input_type="url", title=title, company=company, text=page.text,
                    source_url=_clean_url(page.final_url), truncated=page.truncated)


@router.post("/upload", response_model=AnalysisDetail, status_code=201, dependencies=[Depends(rate_limit)])
async def create_analysis_from_file(file: UploadFile = File(...), job_title: str | None = Form(default=None, max_length=200),
                                    company_name: str | None = Form(default=None, max_length=200),
                                    db: Session = Depends(get_db), owner: str = Depends(get_owner),
                                    settings: Settings = Depends(get_settings_dep), det: Detector = Depends(get_detector)):
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise AppError(413, "file_too_large", f"The file is larger than {settings.max_upload_bytes // (1024 * 1024)} MB.")
    def work():
        text, truncated = extract_text(file.filename or "", data, settings.max_pdf_pages, settings.max_text_chars)
        return _analyse(db, owner, settings, det, input_type="file", title=(job_title or "").strip(),
                        company=(company_name or "").strip(), text=text, source_url=None, truncated=truncated)
    return await run_in_threadpool(work)


@router.get("", response_model=Page)
def list_analyses(page: int = Query(1, ge=1, le=10000), page_size: int = Query(10, ge=1, le=50),
                  risk_level: Literal["low", "medium", "high"] | None = None,
                  status: Literal["completed", "failed"] | None = None,
                  q: str | None = Query(None, max_length=100),
                  sort: Literal["newest", "oldest", "risk_desc", "risk_asc"] = "newest",
                  db: Session = Depends(get_db), owner: str = Depends(get_owner)):
    rows, total = repo.list_page(db, owner, page=page, page_size=page_size, risk_level=risk_level, status=status, q=q, sort=sort)
    return Page(items=[AnalysisSummary.model_validate(r) for r in rows], page=page, page_size=page_size, total=total,
                total_pages=max(1, math.ceil(total / page_size)))


@router.get("/{analysis_id}", response_model=AnalysisDetail)
def get_analysis(analysis_id: uuid.UUID, db: Session = Depends(get_db), owner: str = Depends(get_owner)):
    a = repo.get_one(db, owner, analysis_id)
    if not a:
        raise AppError(404, "not_found", "Analysis not found.")
    return to_detail(a)


@router.delete("/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: uuid.UUID, db: Session = Depends(get_db), owner: str = Depends(get_owner)):
    if not repo.delete_one(db, owner, analysis_id):
        raise AppError(404, "not_found", "Analysis not found.")
    return Response(status_code=204)
