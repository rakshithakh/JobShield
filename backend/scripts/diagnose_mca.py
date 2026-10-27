"""Safe diagnostic for the data.gov.in MCA company-master resource. Makes AT MOST 2 live calls and stops at the first failure.

    cd backend
    python -m scripts.diagnose_mca                 # default test name: INFOSYS LIMITED
    python -m scripts.diagnose_mca "TATA MOTORS LIMITED"

Call 1 (no filter, limit=1) answers: is the service reachable, does the key work, what do the records look like (field names).
Call 2 (only if call 1 worked) tests whether an exact-name filter on the detected name field returns matching records.
The API key is read from backend/.env or the environment and is NEVER printed (also scrubbed from error text and bodies).
Exit codes: 0 exact-name filter verified | 1 service works but the name filter is NOT verified | 2 not configured | 3 service/network problem.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

DEFAULT_RESOURCE = "4dbe5667-7b6b-41d7-82af-211562424d9a"
URL = "https://api.data.gov.in/resource/{rid}"
SNIPPET = 500


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.split(" #")[0].strip().strip("'\"")
    return out


def sanitise(text: str, key: str) -> str:
    if key:
        text = text.replace(key, "***")
    return re.sub(r"(api[-_]?key=)[^&\s\"']+", r"\1***", text, flags=re.I)


def norm(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", name.upper()).strip()


@dataclass
class Probe:
    kind: str                 # ok | timeout | connection_error | auth_error | rate_limited | server_error | http_error | invalid_json | unexpected_shape
    status: int | None
    ms: int
    detail: str
    data: dict | None = None


def probe(client: httpx.Client, rid: str, key: str, params: dict[str, str | int]) -> Probe:
    t0 = time.perf_counter()
    ms = lambda: int((time.perf_counter() - t0) * 1000)  # noqa: E731
    try:
        r = client.get(URL.format(rid=rid), params={"api-key": key, "format": "json", **params})
    except httpx.ConnectTimeout:
        return Probe("timeout", None, ms(), "ConnectTimeout: could not establish a connection within the connect timeout (network, proxy, or firewall).")
    except httpx.ReadTimeout:
        return Probe("timeout", None, ms(), "ReadTimeout: connected, but no response arrived before the read timeout; the service may be slow or hung.")
    except httpx.TimeoutException as e:
        return Probe("timeout", None, ms(), f"{type(e).__name__}: request timed out before a response arrived.")
    except httpx.TransportError as e:
        return Probe("connection_error", None, ms(), f"{type(e).__name__}: {sanitise(str(e), key)[:200]}")
    body = sanitise(r.text[:SNIPPET], key)
    if r.status_code in (401, 403):
        return Probe("auth_error", r.status_code, ms(), body)
    if r.status_code == 429:
        return Probe("rate_limited", 429, ms(), body)
    if r.status_code >= 500:
        return Probe("server_error", r.status_code, ms(), body)
    if r.status_code != 200:
        return Probe("http_error", r.status_code, ms(), body)
    try:
        data = r.json()
    except ValueError:
        return Probe("invalid_json", 200, ms(), body)
    if not isinstance(data, dict):
        return Probe("unexpected_shape", 200, ms(), body)
    return Probe("ok", 200, ms(), "", data)


MEANING = {
    "server_error": "The SERVICE failed (HTTP 5xx) even for a plain, unfiltered request, so your query is not the cause. Do not retry in a loop. "
                    "Try again later; if it persists, contact data.gov.in support with the resource id and the time. The app stays inconclusive meanwhile.",
    "auth_error": "The key was rejected or is not enabled for this resource. Check MCA_API_KEY in backend/.env (no quotes/spaces) and your data.gov.in profile.",
    "rate_limited": "Rate limit reached. Wait and try later.",
    "connection_error": "Could not connect. This is a network problem on this machine (DNS, firewall, proxy, VPN, antivirus) and not an API answer.",
    "timeout": "For ReadTimeout, try again later or increase --timeout (up to 300 seconds). For ConnectTimeout, check network, proxy, or firewall settings.",
    "invalid_json": "The server answered 200 but not with JSON. Possibly an HTML error page from a gateway.",
    "unexpected_shape": "The server answered 200 with JSON that is not an object.",
    "http_error": "Unexpected HTTP status; see the body snippet.",
}


def detect_fields(data: dict) -> tuple[list[str], str | None, str | None]:
    recs = data.get("records")
    keys = list(recs[0].keys()) if isinstance(recs, list) and recs and isinstance(recs[0], dict) else []
    name = next((k for k in keys if k.lower() == "companyname"), None) or next((k for k in keys if re.search(r"company.*name|^name$", k, re.I)), None)
    status = next((k for k in keys if re.search(r"status", k, re.I)), None)
    return keys, name, status


def main(argv: list[str] | None = None, client: httpx.Client | None = None, env: dict[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely diagnose the data.gov.in MCA resource (at most two requests).")
    parser.add_argument("--timeout", type=float, default=15.0, metavar="SECONDS", help="response timeout (default: 15; max: 300)")
    parser.add_argument("company", nargs="?", default="INFOSYS LIMITED", help="company name to test (default: INFOSYS LIMITED)")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if not 0 < args.timeout <= 300:
        parser.error("--timeout must be greater than 0 and no more than 300 seconds")
    test_name = args.company
    env = env if env is not None else {**load_env(Path(".env")), **{k: v for k, v in os.environ.items() if k.startswith("MCA_")}}
    key, rid = env.get("MCA_API_KEY", ""), env.get("MCA_RESOURCE_ID") or DEFAULT_RESOURCE
    if not key:
        print("MCA_API_KEY is not set in backend/.env. (Run this from the backend folder.)")
        return 2
    own = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(args.timeout, connect=min(5.0, args.timeout)))
    calls = 0
    try:
        print(f"Resource: {rid}\n\nCall 1: unfiltered, limit=1")
        p1 = probe(client, rid, key, {"limit": 1})
        calls += 1
        print(f"  result: {p1.kind}  http={p1.status}  {p1.ms} ms")
        if p1.kind != "ok":
            print(f"  body/detail: {p1.detail or '(empty)'}\n  meaning: {MEANING.get(p1.kind, '')}")
            print(f"\nStopped after {calls} call (no point calling further). The MCA check stays 'inconclusive' in the app.")
            return 3
        assert p1.data is not None
        keys, name_field, status_field = detect_fields(p1.data)
        print(f"  top-level keys: {sorted(p1.data.keys())}\n  record fields: {keys or '(none returned)'}")
        print(f"  detected name field: {name_field}   status field: {status_field}")
        if not name_field:
            print("\nNo company-name field was detected, so the name filter cannot be tested. Send me the field list above (it contains no secrets).")
            return 1
        print(f"\nCall 2: exact-name filter  filters[{name_field}]={test_name!r}, limit=5")
        p2 = probe(client, rid, key, {"limit": 5, f"filters[{name_field}]": test_name})
        calls += 1
        print(f"  result: {p2.kind}  http={p2.status}  {p2.ms} ms")
        if p2.kind != "ok":
            print(f"  body/detail: {p2.detail or '(empty)'}\n  meaning: {MEANING.get(p2.kind, '')}")
            return 3
        assert p2.data is not None
        recs = [r for r in (p2.data.get("records") or []) if isinstance(r, dict)]
        names = [str(r.get(name_field, "")) for r in recs]
        print(f"  records returned: {len(recs)}   names: {names[:5]}")
        if recs and all(norm(n) == norm(test_name) for n in names):
            print(f"\nVERIFIED for this one test: the exact-name filter works.\nAdd to backend/.env:\n  MCA_NAME_FIELD={name_field}\n  MCA_STATUS_FIELD={status_field or ''}")
            return 0
        if recs:
            print("\nNOT verified: the filter returned records whose names differ from the query (partial/other matching). Do not trust it as exact.")
        else:
            print("\nNOT verified: no records. The filter may be unsupported, case-sensitive, or the name spelled differently. One test is not proof either way.")
        return 1
    finally:
        print(f"\nLive calls made: {calls} (maximum 2)")
        if own:
            client.close()


if __name__ == "__main__":
    sys.exit(main())
