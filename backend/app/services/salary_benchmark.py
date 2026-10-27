"""Real salary benchmarks from Adzuna's salary-histogram endpoint (replaces the hand-written table when configured).

    GET https://api.adzuna.com/v1/api/jobs/{country}/histogram?app_id=..&app_key=..&what=<job title>
    -> {"histogram": {"<annual salary>": <number of listings>, ...}}      (only listings that state a salary)

Honest limits: coverage for India may be thin, Adzuna says some salaries are modelled rather than stated, and `what` matches keywords
anywhere in a listing. So a benchmark is used only when it rests on at least MIN_LISTINGS listings across several salary points;
otherwise the caller falls back to the (unsourced) table and says so.

Cache: key = (country, lower-cased job title), value = the benchmark or "insufficient data", TTL 24 h (salary distributions move slowly),
failures are cached for 60 s so an outage or rate limit does not trigger a request storm. Keys hold job titles only, no user text or identifiers.
Privacy: only the job title is sent to Adzuna.
"""
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from ..config import Settings
from .types import DetectionPath

log = logging.getLogger("jobsentinel.salary_benchmark")
MIN_LISTINGS = 30
MIN_DISTINCT_POINTS = 4
CACHE_TTL_SECONDS = 24 * 3600
FAILURE_TTL_SECONDS = 60
MAX_CACHE_ENTRIES = 512


@dataclass(frozen=True)
class Benchmark:
    low: float        # 10th percentile of advertised annual salaries
    median: float
    high: float       # 90th percentile
    listings: int
    query: str
    source: str = "adzuna"


class SalaryBenchmarkProvider(Protocol):
    def lookup(self, query: str) -> tuple[Benchmark | None, DetectionPath]: ...


def weighted_percentile(points: list[tuple[float, int]], q: float) -> float:
    """q in [0,1] over (value, weight) pairs."""
    pts = sorted(points)
    total = sum(w for _, w in pts)
    target = q * total
    run = 0
    for value, weight in pts:
        run += weight
        if run >= target:
            return value
    return pts[-1][0]


def parse_histogram(data: object) -> list[tuple[float, int]] | None:
    """Validated (salary, count) pairs, or None if the response has an unexpected shape."""
    hist = data.get("histogram") if isinstance(data, dict) else None
    if not isinstance(hist, dict):
        return None
    out: list[tuple[float, int]] = []
    for k, v in hist.items():
        try:
            salary, count = float(k), int(v)
        except (TypeError, ValueError):
            continue
        if salary > 0 and count > 0:
            out.append((salary, count))
    return out


def normalise_query(q: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s+#.-]", " ", q.lower())).strip()[:100]


class AdzunaSalaryBenchmarks:
    URL = "https://api.adzuna.com/v1/api/jobs/{country}/histogram"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.s, self.client = settings, client
        self._cache: dict[tuple[str, str], tuple[float, Benchmark | None, DetectionPath]] = {}
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.s.adzuna_salary_benchmarks and self.s.adzuna_app_id and self.s.adzuna_app_key)

    def lookup(self, query: str) -> tuple[Benchmark | None, DetectionPath]:
        if not self.configured:
            return None, DetectionPath("adzuna_salary", "not_configured", "ADZUNA_* not set (using the unsourced fallback table)")
        q = normalise_query(query)
        if not q:
            return None, DetectionPath("adzuna_salary", "skipped", "no job title to look up")
        country = re.sub(r"[^a-z]", "", self.s.adzuna_country.lower()) or "in"
        key = (country, q)
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] > now:
                return hit[1], DetectionPath(hit[2].name, hit[2].status, hit[2].detail + " (cached)")
        result = self._fetch(country, q)
        ttl = FAILURE_TTL_SECONDS if result[1].status == "failed" else CACHE_TTL_SECONDS
        with self._lock:
            if len(self._cache) >= MAX_CACHE_ENTRIES:
                self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
                if len(self._cache) >= MAX_CACHE_ENTRIES:
                    self._cache.clear()
            self._cache[key] = (now + ttl, *result)
        return result

    def _fetch(self, country: str, q: str) -> tuple[Benchmark | None, DetectionPath]:
        started = time.perf_counter()
        client = self.client or httpx.Client(timeout=httpx.Timeout(self.s.adzuna_timeout_seconds, connect=3.0))
        try:
            resp = client.get(self.URL.format(country=country),
                              params={"app_id": self.s.adzuna_app_id, "app_key": self.s.adzuna_app_key, "what": q,
                                      "content-type": "application/json"})
            ms = int((time.perf_counter() - started) * 1000)
            if resp.status_code != 200:
                return self._failed("rate_limited" if resp.status_code == 429 else f"http_{resp.status_code}", ms)
            pts = parse_histogram(resp.json())
            if pts is None:
                return self._failed("unexpected_response_shape", ms)
            n = sum(w for _, w in pts)
            if n < MIN_LISTINGS or len(pts) < MIN_DISTINCT_POINTS:
                return None, DetectionPath("adzuna_salary", "ok", f"only {n} listings with a stated salary for '{q}': too few to use")
            bench = Benchmark(weighted_percentile(pts, 0.10), weighted_percentile(pts, 0.50), weighted_percentile(pts, 0.90), n, q)
            return bench, DetectionPath("adzuna_salary", "ok", f"{n} listings for '{q}'")
        except (httpx.TimeoutException, httpx.TransportError):
            return self._failed("timeout_or_network_error", int((time.perf_counter() - started) * 1000))
        except ValueError:
            return self._failed("invalid_json", int((time.perf_counter() - started) * 1000))
        finally:
            if self.client is None:
                client.close()

    @staticmethod
    def _failed(reason: str, ms: int) -> tuple[None, DetectionPath]:
        log.warning("adzuna_salary_unavailable", extra={"provider": "adzuna_salary", "latency_ms": ms, "outcome": reason})
        return None, DetectionPath("adzuna_salary", "failed", reason)
