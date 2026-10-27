"""Probe the official data.gov.in MCA21 resource without exposing its API key.

Run from the backend directory with:
    python scripts/test_mca21_api.py
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from urllib.parse import quote, quote_plus

import httpx


RESOURCE_ID = "4dbe5667-7b6b-41d7-82af-211562424d9a"
COMPANY_QUERY = "Infosys Limited"
API_URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"


def _read_env_key() -> str:
    """Read MCA_API_KEY from backend/.env, falling back to the process env."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.is_file():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == "MCA_API_KEY":
                value = value.strip().strip("\"'")
                if value:
                    return value
    return os.environ.get("MCA_API_KEY", "").strip()


def _normalise(value: object) -> str:
    return " ".join(str(value or "").upper().split())


def main() -> int:
    api_key = _read_env_key()
    if not api_key:
        print("API key not found in backend/.env or MCA_API_KEY environment variable.")
        return 2

    params = {
        "api-key": api_key,
        "format": "json",
        "limit": 10,
        "filters[CompanyName]": COMPANY_QUERY.upper(),
    }
    try:
        response = httpx.get(
            API_URL,
            params=params,
            timeout=httpx.Timeout(connect=15.0, read=90.0, write=15.0, pool=15.0),
        )
    except httpx.RequestError as exc:
        # Exception messages can include a prepared URL; emit only its type.
        print(f"Request failed: {type(exc).__name__}")
        return 1

    print(f"HTTP status: {response.status_code}")
    try:
        payload = response.json()
    except ValueError:
        print("Returned field names: unavailable (response was not JSON)")
        print("Matching record found: no")
        if response.is_error:
            preview = response.text[:400].replace(api_key, "[redacted]")
            preview = preview.replace(quote(api_key, safe=""), "[redacted]")
            preview = preview.replace(quote_plus(api_key), "[redacted]")
            preview = " ".join(preview.split())
            print(f"Error response preview: {preview or '(empty body)'}")
        return 1

    records = payload.get("records", []) if isinstance(payload, dict) else []
    fields: set[str] = set()
    matching = False
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, dict):
                continue
            fields.update(record.keys())
            if _normalise(record.get("CompanyName")) == _normalise(COMPANY_QUERY):
                matching = True

    print("Returned field names: " + (", ".join(sorted(fields)) if fields else "none"))
    print(f"Matching record found: {'yes' if matching else 'no'}")
    if response.is_error:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
