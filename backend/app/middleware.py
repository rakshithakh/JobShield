import logging
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("jobsentinel.http")


class BodyLimitMiddleware:
    """Rejects request bodies larger than max_bytes (checks Content-Length and counts streamed bytes)."""

    def __init__(self, app: ASGIApp, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        cl = Headers(scope=scope).get("content-length")
        if cl and cl.isdigit() and int(cl) > self.max_bytes:
            return await self._reject(scope, receive, send)
        seen = 0
        too_big = False

        async def limited_receive() -> Message:
            nonlocal seen, too_big
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > self.max_bytes:
                    too_big = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return msg

        started = False

        async def guarded_send(message: Message):
            nonlocal started
            if too_big and not started:
                started = True
                await self._reject(scope, receive, send)
                return
            if not too_big:
                await send(message)

        await self.app(scope, limited_receive, guarded_send)

    async def _reject(self, scope, receive, send):
        from starlette.responses import JSONResponse
        resp = JSONResponse({"error": {"code": "payload_too_large", "message": "The request is too large."}}, status_code=413)
        await resp(scope, receive, send)


class RequestContextMiddleware:
    """Request id, timing, structured access log, and conservative response headers."""

    def __init__(self, app: ASGIApp, hsts: bool = False):
        self.app, self.hsts = app, hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        is_docs = scope["path"].startswith(("/docs", "/redoc", "/openapi.json"))
        rid = uuid.uuid4().hex[:16]
        scope.setdefault("state", {})["request_id"] = rid
        start = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                h = MutableHeaders(scope=message)
                h["X-Request-ID"] = rid
                h["X-Content-Type-Options"] = "nosniff"
                h["Referrer-Policy"] = "no-referrer"
                h["Cache-Control"] = "no-store"
                h["X-Frame-Options"] = "DENY"
                h["Cross-Origin-Resource-Policy"] = "same-site"
                if not is_docs:   # Swagger UI needs its CDN assets; the JSON API itself never renders content
                    h["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
                if self.hsts:
                    h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
                h["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
                h["X-Response-Time-ms"] = str(int((time.perf_counter() - start) * 1000))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            log.info("request", extra={"request_id": rid, "method": scope["method"], "path": scope["path"],
                                       "status": status, "duration_ms": int((time.perf_counter() - start) * 1000)})
