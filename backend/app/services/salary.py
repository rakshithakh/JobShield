"""Salary plausibility check against app/data/salary_benchmarks.json.

The benchmark table is a hand-written, UNSOURCED approximation of annual INR pay carried over from the original
project. It is a rough sanity check only and is labelled as such in every signal it produces.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from .types import DetectionPath, Signal

if TYPE_CHECKING:
    from .salary_benchmark import SalaryBenchmarkProvider

DATA = Path(__file__).resolve().parent.parent / "data" / "salary_benchmarks.json"

_MONTHLY = [
    re.compile(r"(?:rs\.?|inr|₹|earn|salary|package|stipend|ctc)[/\s.]*(\d+(?:,\d+)*)\s*(?:/-\s*)?(?:per\s*month|/month|monthly|month\b)", re.I),
    re.compile(r"(\d+(?:,\d+)*)\s*(?:rs\.?|₹)\s*(?:per\s*month|/month|monthly)", re.I),
    re.compile(r"(\d+)k\s*(?:per\s*month|/month)", re.I),
]
_ANNUAL = [
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac|lpa|l\.p\.a)", re.I),
    re.compile(r"ctc[:\s]+(\d+(?:\.\d+)?)\s*(?:lakh|lac|lpa)", re.I),
]


@lru_cache
def load_benchmarks() -> dict[str, dict[str, int]]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def parse_salary(text: str) -> tuple[float, str] | None:
    """Returns (annual_inr, display) for the first salary figure found, else None."""
    for i, rx in enumerate(_MONTHLY):
        m = rx.search(text)
        if m:
            try:
                val = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if i == 2:
                val *= 1000
            annual = val * 12
            return annual, f"₹{val:,.0f}/month (≈₹{annual / 100000:.1f} LPA)"
    for rx in _ANNUAL:
        m = rx.search(text)
        if m:
            val = float(m.group(1))
            return val * 100000, f"₹{val:.1f} LPA"
    return None


def match_role(title: str, text: str) -> str | None:
    """Best benchmark role: all of its words appear as whole words; title matches win, then longest role name."""
    def words(s): return set(re.findall(r"[a-z]+", s.lower()))
    tw, aw = words(title), words(title + " " + text)
    best, best_key = None, (-1, -1)
    for role in load_benchmarks():
        rw = set(role.split())
        if rw <= aw:
            key = (1 if rw <= tw else 0, len(rw))
            if key > best_key:
                best, best_key = role, key
    return best


def _classify(annual: float, display: str, lo: float, hi: float, role: str, basis: str) -> list[Signal]:
    """Same thresholds for either benchmark source. `basis` says where the range comes from."""
    rng = f"₹{lo / 100000:.1f}L–₹{hi / 100000:.1f}L"
    if annual > hi * 2.0:
        return [Signal("salary:unrealistic_high", "salary", "Salary far above typical range", "high", 30,
                       f"{display} is more than 2× the top of the typical range for '{role}' ({rng}). {basis}", display)]
    if annual > hi * 1.3:
        return [Signal("salary:above_market", "salary", "Salary above typical range", "medium", 15,
                       f"{display} is above the typical range for '{role}' ({rng}). {basis}", display)]
    if annual < lo * 0.6:
        return [Signal("salary:below_market", "salary", "Salary unusually low", "low", 8,
                       f"{display} is well below the typical range for '{role}' ({rng}). {basis}", display)]
    return [Signal("salary:in_range", "salary", "Salary within typical range", "info", 0,
                   f"{display} falls within the typical range for '{role}' ({rng}). This does not lower the risk score. {basis}", display)]


def analyze_salary(title: str, text: str) -> list[Signal]:
    """Fallback: hand-written, UNSOURCED table (kept for when no live benchmark is available)."""
    parsed = parse_salary(text)
    if not parsed:
        return [Signal("salary:none", "salary", "No salary figure found", "info", 0, "No monthly or LPA salary could be parsed from the text.")]
    annual, display = parsed
    role = match_role(title, text)
    note = "(Benchmarks are rough, unsourced estimates.)"
    if not role:
        return [Signal("salary:no_benchmark", "salary", f"Salary stated: {display}", "info", 0,
                       "This role is not in the benchmark table, so no comparison was made. " + note, display)]
    b = load_benchmarks()[role]
    return _classify(annual, display, b["min"], b["max"], role, note)


def analyze_salary_live(title: str, text: str, provider: "SalaryBenchmarkProvider | None") -> tuple[list[Signal], list[DetectionPath]]:
    """Prefer real Adzuna advertised-salary percentiles; fall back to the table. Returns (signals, extra detection paths)."""
    parsed = parse_salary(text)
    if not parsed:
        return analyze_salary(title, text), [DetectionPath("adzuna_salary", "skipped", "no salary figure in the text")]
    if provider is None:
        return analyze_salary(title, text), []
    annual, display = parsed
    query = title.strip() or match_role(title, text) or ""
    bench, path = provider.lookup(query)
    if bench is None:
        return analyze_salary(title, text), [path]
    basis = (f"Source: Adzuna advertised salaries for '{bench.query}' ({bench.listings} listings with a stated salary; "
             f"10th–90th percentile, median ₹{bench.median / 100000:.1f}L). Some advertised salaries are modelled.")
    return _classify(annual, display, bench.low, bench.high, bench.query, basis), [path]
