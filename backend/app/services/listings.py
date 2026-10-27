"""Optional cross-check: does a job with this title at this company appear on the Adzuna aggregator?

INFORMATION ONLY (0 points). Scammers copy real postings, so a match does not make a posting genuine, and Adzuna covers only a
slice of the market, so no match is inconclusive. Request/response shape follows Adzuna's public search API as documented;
it has NOT been verified live here (no credentials). Disabled unless ADZUNA_APP_ID and ADZUNA_APP_KEY are set.
"""
import logging
import re
import time
from urllib.parse import urlsplit

import httpx

from ..config import Settings
from .types import CompanyCheck, DetectionPath

log = logging.getLogger("jobsentinel.listings")
_SUFFIX = {"ltd", "limited", "pvt", "private", "inc", "llc", "llp", "corp", "corporation", "co", "company", "india", "technologies", "technology", "services", "solutions"}


def _norm(name: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", name.lower()) if t not in _SUFFIX]


def _same_company(a: str, b: str) -> bool:
    ta, tb = _norm(a), _norm(b)
    return bool(ta) and ta == tb


def _safe_url(u: object) -> str | None:
    if isinstance(u, str) and urlsplit(u).scheme in ("http", "https"):
        return u[:2048]
    return None


class AdzunaListingProvider:
    URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.s, self.client = settings, client

    @property
    def configured(self) -> bool:
        return bool(self.s.adzuna_app_id and self.s.adzuna_app_key)

    def lookup(self, company: str, title: str) -> tuple[CompanyCheck, DetectionPath]:
        if not self.configured:
            return (CompanyCheck("adzuna_listing", "not_configured", "Job-board listing check is not configured on this server."),
                    DetectionPath("adzuna", "not_configured", "ADZUNA_APP_ID / ADZUNA_APP_KEY not set"))
        if not company.strip():
            return (CompanyCheck("adzuna_listing", "not_provided", "No company name, so no listing check was made."),
                    DetectionPath("adzuna", "skipped", "no company name"))
        started = time.perf_counter()
        client = self.client or httpx.Client(timeout=httpx.Timeout(self.s.adzuna_timeout_seconds, connect=3.0))
        try:
            resp = client.get(self.URL.format(country=re.sub(r"[^a-z]", "", self.s.adzuna_country.lower()) or "in"),
                              params={"app_id": self.s.adzuna_app_id, "app_key": self.s.adzuna_app_key, "results_per_page": 20,
                                      "what": (title or company).strip()[:100], "content-type": "application/json"})
            ms = int((time.perf_counter() - started) * 1000)
            if resp.status_code != 200:
                return self._unavailable("rate_limited" if resp.status_code == 429 else f"http_{resp.status_code}", ms)
            data = resp.json()
            results = data.get("results") if isinstance(data, dict) else None
            if not isinstance(results, list):
                return self._unavailable("unexpected_response_shape", ms)
            for r in results:
                name = ((r.get("company") or {}).get("display_name") if isinstance(r, dict) else None) or ""
                if _same_company(company, str(name)):
                    return (CompanyCheck("adzuna_listing", "listing_found",
                                         "A listing for this company appears on Adzuna. Scammers can copy real listings, so this does not confirm "
                                         "your posting is genuine.", source_url=_safe_url(r.get("redirect_url")), latency_ms=ms),
                            DetectionPath("adzuna", "ok", "match"))
            return (CompanyCheck("adzuna_listing", "listing_not_found",
                                 "No matching listing was found on Adzuna. That is inconclusive: the aggregator covers only part of the market.", latency_ms=ms),
                    DetectionPath("adzuna", "ok", "no match"))
        except (httpx.TimeoutException, httpx.TransportError):
            return self._unavailable("timeout_or_network_error", int((time.perf_counter() - started) * 1000))
        except ValueError:
            return self._unavailable("invalid_json", int((time.perf_counter() - started) * 1000))
        finally:
            if self.client is None:
                client.close()

    @staticmethod
    def _unavailable(reason: str, ms: int):
        log.warning("adzuna_unavailable", extra={"provider": "adzuna", "latency_ms": ms, "outcome": reason})
        return (CompanyCheck("adzuna_listing", "unavailable", "The job-board listing check could not be completed.", latency_ms=ms),
                DetectionPath("adzuna", "failed", reason))
