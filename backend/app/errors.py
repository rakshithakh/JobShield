"""Consistent error type and handlers. Clients never receive stack traces or raw exception text."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("jobsentinel.errors")


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, analysis_id: str | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.analysis_id = analysis_id
        super().__init__(message)


def _body(request: Request, code: str, message: str, details=None, analysis_id=None) -> dict:
    err = {"code": code, "message": message, "request_id": getattr(request.state, "request_id", None)}
    if details:
        err["details"] = details
    if analysis_id:
        err["analysis_id"] = analysis_id
    return {"error": err}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return JSONResponse(_body(request, exc.code, exc.message, analysis_id=exc.analysis_id), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path")), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(_body(request, "validation_error", "The request was not valid.", details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed", 413: "payload_too_large"}.get(exc.status_code, "http_error")
        return JSONResponse(_body(request, code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled_error", extra={"request_id": getattr(request.state, "request_id", None)})
        return JSONResponse(_body(request, "internal_error", "Something went wrong on our side."), status_code=500)
