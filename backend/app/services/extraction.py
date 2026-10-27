"""Text extraction from uploaded files. Supports PDF and plain text only.
PDFs are parsed in a child process (pdf_worker.py) so a hostile file can be killed on timeout and cannot exhaust the API process."""
import json
import subprocess
import sys

from ..errors import AppError

ALLOWED_EXTENSIONS = {".pdf": "application/pdf", ".txt": "text/plain"}
PDF_PARSE_TIMEOUT_SECONDS = 20
_UNREADABLE = "The PDF could not be read (it may be encrypted, scanned images, or damaged). Try pasting the text instead."


def _pdf_text(data: bytes, max_pages: int, max_chars: int, timeout: float = PDF_PARSE_TIMEOUT_SECONDS) -> str:
    try:
        proc = subprocess.run([sys.executable,  # noqa: S603 - fixed argv, input via stdin
                               "-m", "app.services.pdf_worker", str(max_pages), str(max_chars)],
                              input=data, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise AppError(422, "pdf_parse_timeout", "The PDF took too long to read. Try pasting the text instead.") from None
    try:
        result = json.loads(proc.stdout.decode("utf-8", "replace").strip().splitlines()[-1])
    except (IndexError, ValueError):
        raise AppError(422, "pdf_unreadable", _UNREADABLE) from None
    if result.get("error") == "too_many_pages":
        raise AppError(422, "pdf_too_many_pages", f"The PDF has more than {max_pages} pages.")
    if "text" not in result:
        raise AppError(422, "pdf_unreadable", _UNREADABLE) from None
    return result["text"]


def extract_text(filename: str, data: bytes, max_pages: int, max_chars: int) -> tuple[str, bool]:
    """Returns (text, truncated). Raises AppError with a client-safe message."""
    name = (filename or "").lower()
    ext = name[name.rfind("."):] if "." in name else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise AppError(415, "unsupported_file_type", "Only PDF and plain-text (.txt) files are supported.")
    if not data:
        raise AppError(422, "empty_file", "The uploaded file is empty.")
    if ext == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise AppError(415, "unsupported_file_type", "The file does not look like a valid PDF.")
        text = _pdf_text(data, max_pages, max_chars)
    else:
        if b"\x00" in data[:1024]:
            raise AppError(415, "unsupported_file_type", "The file does not look like plain text.")
        text = data.decode("utf-8", errors="replace")
    text = text.strip()
    if len(text) < 20:
        raise AppError(422, "no_text_found", "Not enough readable text was found in the file. Scanned PDFs need OCR, which is not supported.")
    return (text[:max_chars], True) if len(text) > max_chars else (text, False)
