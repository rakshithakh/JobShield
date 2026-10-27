"""Company verification â€” kept separate from job-posting risk.

Statuses (CompanyCheck.status):
  known_employer      name matches the bundled list of well-known employers (does NOT prove the poster is that employer)
  registry_active     found in the MCA21 dataset with a non-struck-off status
  registry_inactive   found, but listed as struck off / dissolved
  registry_not_found  not found by exact-name lookup (INCONCLUSIVE: foreign firms and name variants are missed)
  name_heuristic      name contains a term the original project associated with low-quality earning schemes (weak)
  not_provided        no company name supplied
  not_configured      provider needs credentials that are absent
  unavailable         provider timed out, errored or returned an unusable response
  unknown             nothing could be determined

Unknown / unavailable never add risk points. Only positive evidence (heuristic name match, struck-off registry status) does.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Protocol
import httpx

from ..config import Settings
from .types import CompanyCheck, DetectionPath, Signal

DATA = Path(__file__).resolve().parent.parent / "data" / "trusted_companies.json"
NAME_HEURISTIC_POINTS = 15
INACTIVE_POINTS = 35


@lru_cache
def _data() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _tokens(name: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", name.lower())


def match_known_employer(name: str) -> bool:
    """Whole-token match: the name must be a known employer plus only generic corporate suffixes.
    (The original substring match whitelisted names like 'Ola Earn Fast Jobs'.)"""
    toks = _tokens(name)
    if not toks:
        return False
    suffixes = set(_data()["allowed_name_suffixes"])
    for entry in _data()["trusted_employers"]:
        et = _tokens(entry)
        if toks[: len(et)] == et and all(t in suffixes for t in toks[len(et):]):
            return True
    return False


def match_name_heuristic(name: str) -> str | None:
    squashed = re.sub(r"[^a-z0-9]", "", name.lower())
    for kw in _data()["generic_scheme_name_terms"]:
        if kw in squashed:
            return kw
    return None


class RegistryProvider(Protocol):
    def lookup(self, company_name: str) -> tuple[CompanyCheck, DetectionPath]: ...


class Mca21Provider:
    """MCA21 resource adapter.

    The confirmed resource exposes CompanyStateCode as its only API filter. A
    CompanyName filter is silently ignored, so this resource cannot safely
    answer exact-name lookup or prove a company is absent. Until data.gov.in
    provides a searchable name endpoint, fail closed instead of interpreting
    an unrelated first record as a match.
    """
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.s = settings
        self.client = client

    def lookup(self, company_name: str):
        if not self.s.mca_api_key:
            return (CompanyCheck("mca21", "not_configured", "MCA21 registry lookup is not configured on this server."),
                    DetectionPath("mca21", "not_configured", "MCA_API_KEY not set"))
        return (CompanyCheck(
                    "mca21", "unavailable",
                    "The configured MCA21 resource only supports filtering by state, not reliable company-name lookup. "
                    "No company status or match can be determined from this resource.",
                ),
                DetectionPath("mca21", "unavailable", "unsupported_name_filter"))


class NoCompanySearchProvider:
    """Explicitly report that no online registry/name-search provider is configured."""
    provider_name = "company_search"

    def lookup(self, company_name: str) -> tuple[CompanyCheck, DetectionPath]:
        return (
            CompanyCheck(
                self.provider_name,
                "not_configured",
                "Online company search is disabled. Verify the employer independently on its official website or the MCA portal.",
            ),
            DetectionPath(self.provider_name, "not_configured", "online company search disabled"),
        )


def verify_company(name: str, registry: RegistryProvider) -> tuple[list[CompanyCheck], str, list[DetectionPath], list[Signal]]:
    """Returns (checks, overall_status, detection_paths, risk_signals)."""
    name = (name or "").strip()
    provider_name = getattr(registry, "provider_name", "mca21")
    if not name:
        return ([CompanyCheck("trusted_list", "not_provided", "No company name was provided, so the employer could not be checked.")],
                "not_provided", [DetectionPath(provider_name, "skipped", "no company name")], [])
    checks, paths, signals = [], [], []

    known = match_known_employer(name)
    checks.append(CompanyCheck("trusted_list", "known_employer" if known else "unknown",
                               "The name matches a well-known employer. That does not confirm this posting is genuine." if known
                               else "The name is not in the bundled list of well-known employers (the list is short and not exhaustive)."))
    kw = match_name_heuristic(name)
    if kw:
        checks.append(CompanyCheck("name_heuristic", "name_heuristic",
                                   f"The name contains '{kw}', a term often seen in the names of low-quality earning schemes. "
                                   "Many legitimate businesses use similar words, so this is weak evidence."))
        signals.append(Signal("company:name_heuristic", "company", "Company name resembles generic job-scheme naming", "low",
                              NAME_HEURISTIC_POINTS, "Weak heuristic only; it says nothing about whether the company exists.", name))
    check, path = registry.lookup(name)
    checks.append(check)
    paths.append(path)
    if check.status == "registry_inactive":
        signals.append(Signal("company:registry_inactive", "company", "Company is listed as struck off / dissolved", "high",
                              INACTIVE_POINTS, check.summary, name))

    statuses = {c.status for c in checks}
    overall: str
    for s in ("registry_inactive", "name_heuristic", "known_employer", "registry_active", "registry_not_found"):
        if s in statuses:
            overall = s
            break
    else:
        overall = "unavailable" if "unavailable" in statuses else "unknown"
    return checks, overall, paths, signals
