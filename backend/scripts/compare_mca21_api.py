"""Compare filtered and unfiltered requests to the official MCA21 OGD resource.

Run from the backend directory:
    python scripts/compare_mca21_api.py

Reads MCA_API_KEY from backend/.env (or the process environment) and never prints it.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import quote, quote_plus

import httpx

RESOURCE_ID = "4dbe5667-7b6b-41d7-82af-211562424d9a"
API_URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"
TIMEOUT = httpx.Timeout(connect=15.0, read=90.0, write=15.0, pool=15.0)


def read_api_key() -> str:
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


def safe_preview(response: httpx.Response, api_key: str) -> str:
    preview = response.text[:350]
    for secret in (api_key, quote(api_key, safe=""), quote_plus(api_key)):
        preview = preview.replace(secret, "[redacted]")
    return " ".join(preview.split()) or "(empty)"


def inspect_response(label: str, response: httpx.Response, elapsed: float, api_key: str) -> None:
    print(
        f"{label}: HTTP status={response.status_code}; "
        f"response_time={elapsed:.3f}s; body_empty={not bool(response.content)}"
    )
    print(f"{label}: body_preview={safe_preview(response, api_key)}")
    try:
        payload = response.json()
    except ValueError:
        print(f"{label}: JSON field names=unavailable (non-JSON response)")
        return

    if isinstance(payload, dict):
        top_fields = sorted(payload.keys())
        records = payload.get("records")
        record_fields = (
            sorted(records[0].keys())
            if isinstance(records, list) and records and isinstance(records[0], dict)
            else []
        )
        print(f"{label}: JSON top-level fields={top_fields}; first-record fields={record_fields or 'none'}")
    else:
        print(f"{label}: JSON root type={type(payload).__name__}; object field names=not applicable")


def main() -> int:
    api_key = read_api_key()
    if not api_key:
        print("MCA_API_KEY not found in backend/.env or the process environment.")
        return 2

    cases = (
        ("Unfiltered", {"format": "json", "limit": 1}),
        (
            "Filtered",
            {
                "format": "json",
                "limit": 1,
                "filters[CompanyName]": "Infosys Limited",
            },
        ),
    )
    had_error = False
    with httpx.Client(timeout=TIMEOUT) as client:
        for label, query in cases:
            started = time.perf_counter()
            try:
                response = client.get(API_URL, params={"api-key": api_key, **query})
            except httpx.TimeoutException as exc:
                elapsed = time.perf_counter() - started
                print(
                    f"{label}: timeout={type(exc).__name__}; elapsed={elapsed:.3f}s; "
                    "HTTP status=none; body_empty=unknown; preview=unavailable; JSON fields=unavailable"
                )
                had_error = True
                continue
            except httpx.RequestError as exc:
                elapsed = time.perf_counter() - started
                print(
                    f"{label}: request_error={type(exc).__name__}; elapsed={elapsed:.3f}s; "
                    "HTTP status=none; body_empty=unknown; preview=unavailable; JSON fields=unavailable"
                )
                had_error = True
                continue

            elapsed = time.perf_counter() - started
            inspect_response(label, response, elapsed, api_key)
            had_error |= response.is_error
    return 1 if had_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
