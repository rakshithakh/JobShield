import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AnalyzePage, { validate } from "../pages/AnalyzePage";
import { ApiError, api } from "../lib/api";
import { a11yViolations, detail, renderAt } from "./helpers";

const LONG = "Urgent hiring! Pay Rs 999 registration fee to join our team today.";
beforeEach(() => vi.restoreAllMocks());

describe("validate()", () => {
  const base = { text: "", url: "", file: null, company: "", title: "" };
  it("checks each mode", () => {
    expect(validate("text", { ...base, text: "short" }).text).toBeTruthy();
    expect(validate("text", { ...base, text: LONG })).toEqual({});
    expect(validate("url", { ...base, url: "ftp://x.com" }).url).toBeTruthy();
    expect(validate("url", { ...base, url: "not a url" }).url).toBeTruthy();
    expect(validate("url", { ...base, url: "https://jobs.example.com/1" })).toEqual({});
    expect(validate("file", base).file).toBeTruthy();
    expect(validate("file", { ...base, file: { name: "a.exe", size: 5 } }).file).toMatch(/PDF/);
    expect(validate("file", { ...base, file: { name: "a.pdf", size: 6 * 1024 * 1024 } }).file).toMatch(/5 MB/);
  });
});

describe("AnalyzePage", () => {
  it("shows inline errors and does not call the API when invalid", async () => {
    const spy = vi.spyOn(api, "createAnalysis");
    renderAt(<AnalyzePage />);
    await userEvent.click(screen.getByRole("button", { name: /analyse posting/i }));
    expect(await screen.findByText(/at least 20 characters/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/job description or message/i)).toHaveAttribute("aria-invalid", "true");
    expect(spy).not.toHaveBeenCalled();
  });

  it("submits text, ignores repeated clicks while loading, then navigates", async () => {
    let resolve;
    const spy = vi.spyOn(api, "createAnalysis").mockImplementation(() => new Promise((r) => { resolve = r; }));
    renderAt(<AnalyzePage />, { path: "/analyze", route: "/analyze" });
    await userEvent.type(screen.getByLabelText(/job description or message/i), LONG);
    await userEvent.type(screen.getByLabelText(/company name/i), "Acme");
    const btn = screen.getByRole("button", { name: /analyse posting/i });
    await userEvent.dblClick(btn);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith({ company_name: "Acme", job_text: LONG });
    expect(screen.getByRole("button", { name: /analysing/i })).toBeDisabled();
    resolve(detail());
    expect(await screen.findByText(/NAVIGATED/)).toBeInTheDocument();
  });

  it("shows API errors with a working retry", async () => {
    const spy = vi.spyOn(api, "createAnalysis")
      .mockRejectedValueOnce(new ApiError(500, "server_error", "The server could not complete the request.", "req123"))
      .mockResolvedValueOnce(detail());
    renderAt(<AnalyzePage />);
    await userEvent.click(screen.getByRole("radio", { name: /web page link/i }));
    await userEvent.type(screen.getByLabelText(/link to the job posting/i), "https://jobs.example.com/1");
    await userEvent.click(screen.getByRole("button", { name: /analyse posting/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not complete the request/i);
    expect(screen.getByText(/Reference: req123/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
    expect(spy).toHaveBeenLastCalledWith({ job_url: "https://jobs.example.com/1" });
  });

  it("offers paste-text analysis when a job page blocks automated fetching", async () => {
    const spy = vi.spyOn(api, "createAnalysis").mockRejectedValueOnce(
      new ApiError(502, "url_fetch_failed", "The page returned HTTP 403. It may require login or block automated access.", "req403", undefined, "analysis-1"),
    );
    renderAt(<AnalyzePage />);
    await userEvent.click(screen.getByRole("radio", { name: /web page link/i }));
    await userEvent.type(screen.getByLabelText(/link to the job posting/i), "https://careers.example.com/jobs/123");
    await userEvent.click(screen.getByRole("button", { name: /analyse posting/i }));

    expect(await screen.findByText(/no score was assigned/i)).toBeInTheDocument();
    expect(screen.getByText(/reference: req403/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /paste job text instead/i }));
    expect(screen.getByLabelText(/job description or message/i)).toBeInTheDocument();
    expect(screen.queryByText(/no score was assigned/i)).not.toBeInTheDocument();
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("maps server field errors back onto the form", async () => {
    vi.spyOn(api, "createAnalysis").mockRejectedValue(new ApiError(422, "validation_error", "The request was not valid.", "r", [{ field: "job_text", message: "too long" }]));
    renderAt(<AnalyzePage />);
    await userEvent.type(screen.getByLabelText(/job description or message/i), LONG);
    await userEvent.click(screen.getByRole("button", { name: /analyse posting/i }));
    expect(await screen.findByText("too long")).toBeInTheDocument();
  });

  it("uploads a chosen file and rejects unsupported types", async () => {
    const up = vi.spyOn(api, "uploadAnalysis").mockResolvedValue(detail());
    renderAt(<AnalyzePage />);
    await userEvent.click(screen.getByRole("radio", { name: /upload file/i }));
    const input = screen.getByLabelText(/offer letter or job description/i);
    await userEvent.upload(input, new File(["x"], "offer.pdf", { type: "application/pdf" }), { applyAccept: false });
    await userEvent.click(screen.getByRole("button", { name: /analyse posting/i }));
    await waitFor(() => expect(up).toHaveBeenCalledTimes(1));
    expect(up.mock.calls[0][0].file.name).toBe("offer.pdf");
  });

  it("rejects a bad file client-side", async () => {
    const up = vi.spyOn(api, "uploadAnalysis");
    renderAt(<AnalyzePage />);
    await userEvent.click(screen.getByRole("radio", { name: /upload file/i }));
    await userEvent.upload(screen.getByLabelText(/offer letter/i), new File(["x"], "virus.exe"), { applyAccept: false });
    await userEvent.click(screen.getByRole("button", { name: /analyse posting/i }));
    expect(await screen.findByText(/only pdf and .txt/i)).toBeInTheDocument();
    expect(up).not.toHaveBeenCalled();
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = renderAt(<AnalyzePage />);
    expect(await a11yViolations(container)).toEqual([]);
  });
});
