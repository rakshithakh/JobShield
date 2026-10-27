import io

import httpx
import pytest
from reportlab.pdfgen import canvas

from app.errors import AppError
from app.services.extraction import extract_text
from app.services.url_fetcher import UnsafeUrl, fetch_job_page, html_to_text, validate_and_resolve
from tests.conftest import make_settings

PUBLIC = lambda host, port: ["93.184.216.34"]


@pytest.mark.parametrize("url", [
    "ftp://example.com/x", "file:///etc/passwd", "gopher://example.com", "javascript:alert(1)",
    "http://127.0.0.1/", "http://localhost/admin", "http://10.0.0.5/", "http://192.168.1.1/", "http://172.16.0.1/",
    "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "http://[::ffff:127.0.0.1]/", "http://0.0.0.0/",
    "http://100.64.0.1/", "http://224.0.0.1/", "http://user:pass@example.com/", "http://example.com:22/", "http://example.com:8080/",
    "http://metadata.internal/", "http:///nohost",
])
def test_unsafe_urls_rejected(url):
    with pytest.raises(UnsafeUrl):
        validate_and_resolve(url, PUBLIC)


def test_hostname_resolving_to_private_ip_rejected():
    with pytest.raises(UnsafeUrl):
        validate_and_resolve("http://evil.example/", lambda h, p: ["10.1.2.3"])


def test_any_private_address_among_many_rejects():
    with pytest.raises(UnsafeUrl):
        validate_and_resolve("http://mixed.example/", lambda h, p: ["93.184.216.34", "127.0.0.1"])


def test_public_url_ok():
    scheme, host, port, path, ips = validate_and_resolve("https://jobs.example.com/p/1?id=2", PUBLIC)
    assert (scheme, host, port, path) == ("https", "jobs.example.com", 443, "/p/1?id=2")


def html_transport(body="<html><head><title>x</title><script>evil()</script></head><body><h1>Backend Engineer</h1><p>Apply now at careers.</p></body></html>", ctype="text/html; charset=utf-8", status=200, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, text=body, headers={"content-type": ctype})
    return httpx.MockTransport(handler)


def test_fetch_pins_ip_and_keeps_host_header():
    seen = []
    page = fetch_job_page("https://jobs.example.com/p/1", make_settings(), PUBLIC, html_transport(seen=seen))
    assert "Backend Engineer" in page.text and "evil()" not in page.text
    assert seen[0].url.host == "93.184.216.34" and seen[0].headers["host"] == "jobs.example.com"


def test_redirect_to_private_address_is_blocked():
    def handler(request):
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})
    with pytest.raises(AppError) as e:
        fetch_job_page("https://jobs.example.com/", make_settings(), PUBLIC, httpx.MockTransport(handler))
    assert e.value.code == "url_not_allowed"


def test_redirect_to_rebinding_hostname_is_revalidated():
    calls = {"n": 0}

    def resolver(host, port):
        return ["93.184.216.34"] if host == "jobs.example.com" else ["127.0.0.1"]

    def handler(request):
        return httpx.Response(301, headers={"location": "https://rebind.example/x"})
    with pytest.raises(AppError) as e:
        fetch_job_page("https://jobs.example.com/", make_settings(), resolver, httpx.MockTransport(handler))
    assert e.value.code == "url_not_allowed"


def test_redirect_loop_is_bounded():
    t = httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "https://jobs.example.com/again"}))
    with pytest.raises(AppError) as e:
        fetch_job_page("https://jobs.example.com/", make_settings(url_fetch_max_redirects=2), PUBLIC, t)
    assert e.value.code == "url_too_many_redirects"


def test_oversized_response_rejected():
    with pytest.raises(AppError) as e:
        fetch_job_page("https://jobs.example.com/", make_settings(url_fetch_max_bytes=100), PUBLIC, html_transport(body="a" * 500))
    assert e.value.code == "url_too_large"


def test_binary_content_type_rejected():
    with pytest.raises(AppError) as e:
        fetch_job_page("https://jobs.example.com/", make_settings(), PUBLIC, html_transport(ctype="application/octet-stream"))
    assert e.value.code == "url_unsupported_content"


def test_http_error_and_timeout_are_client_safe():
    with pytest.raises(AppError) as e:
        fetch_job_page("https://jobs.example.com/", make_settings(), PUBLIC, html_transport(status=403))
    assert e.value.status_code == 502

    def boom(request):
        raise httpx.ReadTimeout("slow")
    with pytest.raises(AppError) as e2:
        fetch_job_page("https://jobs.example.com/", make_settings(), PUBLIC, httpx.MockTransport(boom))
    assert e2.value.code == "url_fetch_failed" and "slow" not in e2.value.message


def test_html_to_text_strips_scripts_and_styles():
    assert html_to_text("<style>a{}</style><p>Hello</p><script>x()</script><div>World</div>") == "Hello\nWorld"


# ---- uploads
def make_pdf(text="Backend Engineer needed. Apply now at our careers site please.", pages=1):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for _ in range(pages):
        c.drawString(72, 750, text)
        c.showPage()
    c.save()
    return buf.getvalue()


def test_pdf_text_extracted():
    text, trunc = extract_text("job.pdf", make_pdf(), 30, 20000)
    assert "Backend Engineer" in text and not trunc


def test_pdf_page_limit():
    with pytest.raises(AppError) as e:
        extract_text("job.pdf", make_pdf(pages=3), 2, 20000)
    assert e.value.code == "pdf_too_many_pages"


@pytest.mark.parametrize("name,data,code", [
    ("evil.exe", b"MZ....", "unsupported_file_type"), ("fake.pdf", b"not a pdf at all", "unsupported_file_type"),
    ("empty.txt", b"", "empty_file"), ("bin.txt", b"abc\x00def" * 10, "unsupported_file_type"),
    ("short.txt", b"hi", "no_text_found"), ("broken.pdf", b"%PDF-1.4 garbage", "pdf_unreadable"),
])
def test_bad_uploads(name, data, code):
    with pytest.raises(AppError) as e:
        extract_text(name, data, 30, 20000)
    assert e.value.code == code


def test_txt_truncated_to_limit():
    text, trunc = extract_text("a.txt", b"x" * 500, 30, 100)
    assert len(text) == 100 and trunc


def test_pdf_parser_runs_in_killable_subprocess(monkeypatch):
    import subprocess

    import app.services.extraction as ex
    real = subprocess.run
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if kw.get("timeout"):
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        return real(cmd, **kw)
    monkeypatch.setattr(ex.subprocess, "run", fake_run)
    with pytest.raises(AppError) as e:
        extract_text("job.pdf", make_pdf(), 30, 20000)
    assert e.value.code == "pdf_parse_timeout" and "pdf_worker" in " ".join(calls[0])


def test_pdf_worker_limits_apply_independently_when_platform_limit_is_missing(monkeypatch):
    import builtins
    from types import SimpleNamespace

    from app.services import pdf_worker

    calls = []
    fake_resource = SimpleNamespace(RLIMIT_CPU=2, setrlimit=lambda key, value: calls.append((key, value)))
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "resource":
            return fake_resource
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    pdf_worker._limit()
    assert calls == [(2, (25, 25))]


def test_pdf_worker_limits_are_optional_when_resource_module_is_unavailable(monkeypatch):
    import builtins

    from app.services import pdf_worker

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "resource":
            raise ImportError("not available on this platform")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    pdf_worker._limit()  # The parent process timeout still bounds the worker on this platform.


def test_fetch_concurrency_cap_returns_503(monkeypatch):
    import app.services.url_fetcher as uf

    class Full:
        def acquire(self, timeout=None): return False
        def release(self): raise AssertionError("must not release unacquired slot")
    monkeypatch.setattr(uf, "_FETCH_SLOTS", Full())
    with pytest.raises(AppError) as e:
        uf.fetch_job_page("https://jobs.example.com/", make_settings(), PUBLIC, html_transport())
    assert e.value.status_code == 503 and e.value.code == "fetch_busy"


def test_pdf_parse_runs_in_killable_child_and_times_out(monkeypatch):
    import subprocess

    from app.services import extraction

    def hang(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)
    monkeypatch.setattr(extraction.subprocess, "run", hang)
    with pytest.raises(AppError) as e:
        extraction.extract_text("a.pdf", make_pdf(), 30, 20000)
    assert e.value.code == "pdf_parse_timeout"


def test_real_child_process_is_actually_killed_on_timeout():
    import subprocess
    import sys
    import time
    t0 = time.time()
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
    assert time.time() - t0 < 5
