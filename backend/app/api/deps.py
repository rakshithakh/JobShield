import hashlib
import re
from collections.abc import Iterator

from fastapi import Header, Request
from sqlalchemy.orm import Session

from ..config import Settings
from ..errors import AppError
from ..services.pipeline import Detector

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-]{32,128}$")


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_detector(request: Request) -> Detector:
    return request.app.state.detector


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def get_owner(x_session_token: str | None = Header(default=None)) -> str:
    """Anonymous per-browser scope. Not authentication: whoever holds the token can see that history."""
    if not x_session_token or not _TOKEN_RE.match(x_session_token):
        raise AppError(401, "missing_session_token", "A valid X-Session-Token header (32-128 URL-safe characters) is required.")
    return hashlib.sha256(x_session_token.encode()).hexdigest()


def client_ip(request: Request, settings: Settings) -> str:
    if settings.trusted_proxy_count > 0:
        fwd = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(fwd) >= settings.trusted_proxy_count:
            return fwd[-settings.trusted_proxy_count]
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request) -> None:
    ok, retry = request.app.state.limiter.check(client_ip(request, request.app.state.settings))
    if not ok:
        raise AppError(429, "rate_limited", f"Too many requests. Try again in {retry} seconds.")
