"""Fetch a job-posting page with SSRF protections.

Controls: http/https only; no credentials in URL; ports 80/443 only; every hostname is resolved and ALL addresses must be
public; the connection is pinned to the validated IP (defeats DNS rebinding) with Host/SNI preserved; redirects are
followed manually and every hop is re-validated; response size, content type and time are capped; no cookies, no proxies.
Pages that require JavaScript or login (many large job boards) cannot be read and return a clear error.
"""
import ipaddress
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from ..config import Settings
from ..errors import AppError

ALLOWED_PORTS = {80, 443}
ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
Resolver = Callable[[str, int], list[str]]
_FETCH_SLOTS = threading.BoundedSemaphore(4)   # at most 4 concurrent outbound fetches per process


class UnsafeUrl(Exception):
    pass


def default_resolver(host: str, port: int) -> list[str]:
    try:
        return sorted({str(ai[4][0]) for ai in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})
    except socket.gaierror as e:
        raise UnsafeUrl("host could not be resolved") from e


def _assert_public(ip_str: str) -> None:
    ip = ipaddress.ip_address(ip_str.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if (not ip.is_global or ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast
            or ip.is_reserved or ip.is_unspecified):
        raise UnsafeUrl("destination is not a public address")


def validate_and_resolve(url: str, resolver: Resolver = default_resolver) -> tuple[str, str, int, str, list[str]]:
    """Returns (scheme, host, port, path_and_query, validated_ips). Raises UnsafeUrl."""
    if len(url) > 2048:
        raise UnsafeUrl("URL too long")
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        raise UnsafeUrl("only http and https URLs are allowed")
    if parts.username or parts.password:
        raise UnsafeUrl("URLs with credentials are not allowed")
    host = parts.hostname
    if not host:
        raise UnsafeUrl("URL has no host")
    host = host.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise UnsafeUrl("destination is not a public address")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as e:
        raise UnsafeUrl("invalid port") from e
    if port not in ALLOWED_PORTS:
        raise UnsafeUrl("only ports 80 and 443 are allowed")
    try:  # IP literal?
        ipaddress.ip_address(host)
        ips = [host]
    except ValueError:
        ips = resolver(host, port)
    if not ips:
        raise UnsafeUrl("host could not be resolved")
    for ip in ips:  # every resolved address must be public
        _assert_public(ip)
    path = urlunsplit(("", "", parts.path or "/", parts.query, ""))
    return parts.scheme, host, port, path, ips


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript", "template", "svg", "head"}
    _BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "ul", "ol"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    p.close()
    lines = [" ".join(line.split()) for line in "".join(p.parts).splitlines()]
    return "\n".join(line for line in lines if line)


@dataclass
class FetchedPage:
    text: str
    final_url: str
    truncated: bool


def fetch_job_page(url: str, s: Settings, resolver: Resolver = default_resolver,
                   transport: httpx.BaseTransport | None = None) -> FetchedPage:
    if not _FETCH_SLOTS.acquire(timeout=2):
        raise AppError(503, "fetch_busy", "Too many page fetches are running. Try again in a moment, or paste the text.")
    try:
        return _fetch(url, s, resolver, transport)
    finally:
        _FETCH_SLOTS.release()


def _fetch(url: str, s: Settings, resolver: Resolver, transport: httpx.BaseTransport | None) -> FetchedPage:
    current = url
    timeout = httpx.Timeout(s.url_fetch_timeout_seconds, connect=min(4.0, s.url_fetch_timeout_seconds))
    for _hop in range(s.url_fetch_max_redirects + 1):
        try:
            scheme, host, port, path, ips = validate_and_resolve(current, resolver)
        except UnsafeUrl as e:
            raise AppError(422, "url_not_allowed", f"This URL cannot be fetched: {e}.") from None
        ip = ips[0]
        netloc_ip = f"[{ip}]" if ":" in ip else ip
        default_port = 443 if scheme == "https" else 80
        pinned = f"{scheme}://{netloc_ip}{'' if port == default_port else f':{port}'}{path}"
        headers = {"Host": host if port == default_port else f"{host}:{port}", "User-Agent": "JobSentinel/1.0 (+job-posting risk checker)",
                   "Accept": "text/html,text/plain;q=0.9", "Accept-Encoding": "identity"}
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False, transport=transport) as client:
                with client.stream("GET", pinned, headers=headers, extensions={"sni_hostname": host}) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("location")
                        if not loc:
                            raise AppError(502, "url_fetch_failed", "The page redirected without a destination.")
                        current = urljoin(current, loc)
                        continue
                    if resp.status_code != 200:
                        raise AppError(502, "url_fetch_failed", f"The page returned HTTP {resp.status_code}. It may require login or block automated access.")
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if ctype not in ALLOWED_CONTENT_TYPES:
                        raise AppError(422, "url_unsupported_content", "The URL does not point to an HTML or text page.")
                    chunks, size = [], 0
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        if size > s.url_fetch_max_bytes:
                            raise AppError(422, "url_too_large", "The page is larger than the allowed size.")
                        chunks.append(chunk)
        except AppError:
            raise
        except (httpx.TimeoutException, httpx.TransportError):
            raise AppError(502, "url_fetch_failed", "The page could not be reached in time.") from None
        raw = b"".join(chunks).decode("utf-8", errors="replace")
        text = html_to_text(raw) if ctype != "text/plain" else raw.strip()
        if len(text) < 20:
            raise AppError(422, "no_text_found", "No readable job text was found at that URL (it may need JavaScript or login). Paste the text instead.")
        truncated = len(text) > s.max_text_chars
        return FetchedPage(text[: s.max_text_chars], current, truncated)
    raise AppError(502, "url_too_many_redirects", "The URL redirected too many times.")
