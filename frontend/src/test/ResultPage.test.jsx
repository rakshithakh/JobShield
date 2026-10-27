import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ResultPage from "../pages/ResultPage";
import { ApiError, api } from "../lib/api";
import { a11yViolations, detail, renderAt } from "./helpers";

const at = () => renderAt(<ResultPage />, { path: "/analyses/:id", route: "/analyses/abc" });
beforeEach(() => vi.restoreAllMocks());

describe("ResultPage", () => {
  it("renders the backend result: score, text label, evidence, unknown company, paths", async () => {
    vi.spyOn(api, "getAnalysis").mockResolvedValue(detail());
    const { container } = at();
    expect(await screen.findByRole("heading", { name: /why this score/i })).toBeInTheDocument();
    expect(screen.getAllByText(/High risk/).length).toBeGreaterThan(0);   // level is text, not colour only
    expect(screen.getByRole("img", { name: /risk score 72 out of 100, high risk/i })).toBeInTheDocument();
    expect(screen.getByText("Pay Rs 999 registration fee")).toBeInTheDocument();
    expect(screen.getByText("+30 points")).toBeInTheDocument();
    expect(screen.getByText(/Unknown: could not be verified/)).toBeInTheDocument();
    expect(screen.queryByText(/fraudulent company/i)).toBeNull();
    expect(screen.getByText("MCA_API_KEY not set")).toBeInTheDocument();
    expect(screen.getByText(/not proof/i)).toBeInTheDocument();
    expect(screen.getByText("Total (capped at 100)")).toBeInTheDocument();
    expect(await a11yViolations(container)).toEqual([]);
  });

  it("shows a job-board listing as information only, with a safe external link", async () => {
    vi.spyOn(api, "getAnalysis").mockResolvedValue(detail({ company_checks: [{ provider: "adzuna_listing", status: "listing_found", summary: "A listing for this company appears. This does not confirm your posting is genuine.", source_url: "https://www.adzuna.in/land/ad/1" }] }));
    at();
    expect(await screen.findByText("Job-board listing (Adzuna)")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Source" });
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.getByText(/does not confirm/i)).toBeInTheDocument();
  });

  it("highlights only the matched phrase, aligned even with emoji before it", async () => {
    const ev = "\u{1F4B0}\u{1F4B0} Earn big. Pay Rs 999 registration fee now";
    const cps = Array.from(ev); const start = cps.join("").indexOf("registration fee"); const a = Array.from(ev.slice(0, start)).length;
    vi.spyOn(api, "getAnalysis").mockResolvedValue(detail({ signals: [{ ...detail().signals[0], evidence: ev, evidence_start: a, evidence_end: a + 16 }] }));
    const { container } = at();
    await screen.findByText("Matched text");
    expect(container.querySelector("mark.evidence").textContent).toBe("registration fee");
  });

  it("shows the cap when the raw total exceeds 100", async () => {
    vi.spyOn(api, "getAnalysis").mockResolvedValue(detail({ risk_score: 100, score_breakdown: { rules: 70, ml: 10, contact: 25, salary: 15, company: 0, raw_total: 120, capped_total: 100 } }));
    at();
    expect(await screen.findByText(/120 → 100/)).toBeInTheDocument();
  });

  it("escapes untrusted evidence text instead of rendering HTML", async () => {
    const evil = '<img src=x onerror="window.__pwn=1"><script>window.__pwn=1</script>';
    vi.spyOn(api, "getAnalysis").mockResolvedValue(detail({ signals: [{ ...detail().signals[0], evidence: evil }] }));
    const { container } = at();
    expect(await screen.findByText(evil)).toBeInTheDocument();
    expect(container.querySelector("img[src='x']")).toBeNull();
    expect(window.__pwn).toBeUndefined();
  });

  it("shows a failed analysis without a score", async () => {
    vi.spyOn(api, "getAnalysis").mockResolvedValue(detail({ status: "failed", risk_score: null, risk_level: null, error_code: "url_fetch_failed", signals: [], company_checks: [] }));
    at();
    expect(await screen.findByText(/did not complete/i)).toBeInTheDocument();
    expect(screen.queryByText(/out of 100/)).toBeNull();
  });

  it("explains that unrelated URL pages were not assessed", async () => {
    vi.spyOn(api, "getAnalysis").mockResolvedValue(detail({
      status: "failed", risk_score: null, risk_level: null, error_code: "not_job_posting",
      input_type: "url", source_url: "https://example.com/", signals: [], company_checks: [],
    }));
    at();
    expect(await screen.findByText("Unable to assess this page")).toBeInTheDocument();
    expect(screen.getByText("Not assessed")).toBeInTheDocument();
    expect(screen.queryByText(/out of 100/)).toBeNull();
  });

  it("handles 404 and server errors with a retry", async () => {
    vi.spyOn(api, "getAnalysis").mockRejectedValueOnce(new ApiError(404, "not_found", "Analysis not found."));
    at();
    expect(await screen.findByText(/analysis not found/i)).toBeInTheDocument();
    expect(screen.getByText(/different browser/i)).toBeInTheDocument();
  });

  it("retries after a server error", async () => {
    const spy = vi.spyOn(api, "getAnalysis").mockRejectedValueOnce(new ApiError(500, "internal_error", "Something went wrong on our side.", "rid9")).mockResolvedValueOnce(detail());
    at();
    const retry = await screen.findByRole("button", { name: /try again/i });
    retry.click();
    expect(await screen.findByRole("heading", { name: /why this score/i })).toBeInTheDocument();
    expect(spy).toHaveBeenCalledTimes(2);
  });
});
