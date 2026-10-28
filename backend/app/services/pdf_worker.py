"""Runs in a child process: reads PDF bytes on stdin, prints one JSON line. The parent kills it on timeout, and memory/CPU
limits are applied (POSIX) so a malicious PDF cannot exhaust the API process."""
import json
import sys


def _set_limit(resource, name: str, amount: int) -> None:
    try:
        limit = getattr(resource, name)
        resource.setrlimit(limit, (amount, amount))
    except (AttributeError, ValueError, OSError):  # unsupported or not permitted by the host
        return


def _limit() -> None:
    try:
        import resource
    except ImportError:  # Windows and other platforms without POSIX resource limits
        return
    # Apply independently so one unsupported limit does not prevent the other from taking effect.
    _set_limit(resource, "RLIMIT_AS", 384 << 20)  # bounded on 512 MiB hosts
    _set_limit(resource, "RLIMIT_CPU", 25)  # CPU seconds


def main() -> int:
    _limit()
    max_pages, max_chars = int(sys.argv[1]), int(sys.argv[2])
    data = sys.stdin.buffer.read()
    try:
        import io

        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as doc:
            if len(doc.pages) > max_pages:
                print(json.dumps({"error": "too_many_pages"}))
                return 0
            parts, total = [], 0
            for page in doc.pages:
                t = page.extract_text() or ""
                parts.append(t)
                total += len(t)
                if total > max_chars * 2:      # enough; stop early
                    break
        print(json.dumps({"text": "\n".join(parts)}))
    except Exception:
        print(json.dumps({"error": "unreadable"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
