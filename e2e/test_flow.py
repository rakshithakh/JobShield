"""Browser end-to-end test: real Chromium -> built React app -> real FastAPI -> real database -> real TF-IDF model.

Run with servers up (see e2e/run.sh), or just `bash e2e/run.sh`.  Screenshots are written to docs/screenshots.
"""
import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:4173")
SHOTS = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
SCAM = ("Urgent hiring! Work from home data entry job. Earn Rs 45000 per month. No experience needed. Only 3 seats left. "
        "Pay Rs 999 registration fee before joining. Daily payment via UPI. Contact: hr.nexgen2024@gmail.com")
REAL = ("We are hiring a Backend Engineer in Pune. 3+ years of Python and PostgreSQL experience. Salary 18 LPA. "
        "We never ask candidates for any fee. Apply via careers@zetalabs.example.com")


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture()
def page(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    yield pg
    assert not errors, f"browser errors: {errors}"
    ctx.close()


def analyse(page, text, company, title):
    page.goto(f"{BASE}/analyze")
    page.get_by_label("Job description or message").fill(text)
    page.get_by_label(re.compile("Company name")).fill(company)
    page.get_by_label(re.compile("Job title")).fill(title)
    page.get_by_role("button", name="Analyse posting").click()
    expect(page.get_by_role("heading", name="Why this score")).to_be_visible(timeout=15000)


def test_full_user_journey(page):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.goto(BASE)
    expect(page.get_by_role("heading", level=1)).to_contain_text("Before you reply")
    expect(page.get_by_text("invented text")).to_be_visible()
    page.screenshot(path=SHOTS / "01-landing.png", full_page=True)

    # README product image uses the self-contained demo, with no stale integration statuses.
    page.goto(f"{BASE}/demo")
    expect(page.get_by_role("heading", name="See how a posting is analysed")).to_be_visible()
    page.screenshot(path=SHOTS / "03-demo.png", full_page=True)

    # empty dashboard / history first (no data yet for this browser)
    page.goto(f"{BASE}/dashboard")
    expect(page.get_by_text("Nothing to summarise yet")).to_be_visible()
    page.goto(f"{BASE}/history")
    expect(page.get_by_text("No analyses yet")).to_be_visible()

    # client-side validation
    page.goto(f"{BASE}/analyze")
    page.get_by_role("button", name="Analyse posting").click()
    expect(page.get_by_text("at least 20 characters")).to_be_visible()
    page.screenshot(path=SHOTS / "02-analyze-validation.png")

    # scam-like posting -> high risk with evidence
    analyse(page, SCAM, "Nexgen Solutions", "Data Entry Operator")
    expect(page.get_by_text("High risk").first).to_be_visible()
    expect(page.get_by_text("Pay Rs 999 registration fee").first).to_be_visible()
    expect(page.get_by_text("Nexgen Solutions: Name resembles generic job-scheme naming (weak signal)")).to_be_visible()
    high_url = page.url

    # genuine-looking posting -> low risk, company unknown (not "fraudulent")
    analyse(page, REAL, "Zeta Labs", "Backend Engineer")
    expect(page.get_by_text("Low risk").first).to_be_visible()
    expect(page.get_by_text("Unknown: could not be verified")).to_be_visible()
    expect(page.locator("body")).not_to_contain_text("fraudulent company")

    # history: persisted in the database, filter + search + detail link
    page.goto(f"{BASE}/history")
    expect(page.get_by_text("2 analyses")).to_be_visible()
    page.get_by_label("Risk level").select_option("high")
    expect(page.get_by_text("1 analysis")).to_be_visible()
    page.get_by_label("Risk level").select_option("")
    page.get_by_label("Search company or title").fill("zeta")
    expect(page.get_by_text("1 analysis")).to_be_visible()
    page.screenshot(path=SHOTS / "05-history.png")
    page.reload()                                             # state survives reload (URL + server)
    expect(page.get_by_role("link", name=re.compile("Backend Engineer"))).to_be_visible()

    # dashboard numbers come from the server
    page.goto(f"{BASE}/dashboard")
    expect(page.get_by_text("Risk levels")).to_be_visible()
    expect(page.get_by_role("img", name=re.compile("1 high, 0 medium, 1 low"))).to_be_visible()
    page.screenshot(path=SHOTS / "06-dashboard.png", full_page=True)

    # persistence across a fresh page load of the detail URL
    page.goto(high_url)
    expect(page.get_by_role("heading", name="Why this score")).to_be_visible()

    # a different browser (new storage) cannot see this analysis
    other = page.context.browser.new_context()
    op = other.new_page()
    op.goto(high_url)
    expect(op.get_by_text("Analysis not found")).to_be_visible()
    other.close()

    # delete
    page.get_by_role("button", name="Delete this analysis").click()
    page.get_by_role("button", name="Yes, delete").click()
    expect(page).to_have_url(re.compile("/history"))
    expect(page.get_by_text("1 analysis")).to_be_visible()


def test_mobile_layout_has_no_horizontal_scroll(browser):
    ctx = browser.new_context(viewport={"width": 375, "height": 800}, is_mobile=True)
    pg = ctx.new_page()
    for path in ("/", "/analyze", "/history", "/about"):
        pg.goto(f"{BASE}{path}")
        scroll = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert scroll <= 1, f"{path} overflows horizontally by {scroll}px"
    pg.goto(BASE)
    pg.screenshot(path=SHOTS / "07-mobile-landing.png", full_page=True)
    ctx.close()


def test_security_headers_reach_the_browser(browser):
    ctx = browser.new_context()
    r = ctx.request.get(f"{BASE}/api/v1/health")
    assert r.status == 200 and "default-src 'none'" in r.headers["content-security-policy"]
    ctx.close()
