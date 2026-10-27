import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import HistoryPage from "../pages/HistoryPage";
import DashboardPage from "../pages/DashboardPage";
import LandingPage from "../pages/LandingPage";
import { ApiError, api } from "../lib/api";
import { a11yViolations, renderAt } from "./helpers";

const item = (i, over = {}) => ({ id: `id-${i}`, created_at: "2026-10-01T10:00:00Z", status: "completed", input_type: "text", job_title: `Role ${i}`, company_name: `Co ${i}`, risk_score: 70, risk_level: "high", company_status: "unknown", ...over });
const page = (items, over = {}) => ({ items, page: 1, page_size: 10, total: items.length, total_pages: 1, ...over });
beforeEach(() => vi.restoreAllMocks());

describe("HistoryPage", () => {
  it("lists analyses from the API and links to details", async () => {
    vi.spyOn(api, "listAnalyses").mockResolvedValue(page([item(1), item(2, { risk_level: "low", risk_score: 3 })]));
    renderAt(<HistoryPage />);
    expect(await screen.findByRole("link", { name: /Role 1/ })).toHaveAttribute("href", "/analyses/id-1");
    expect(screen.getByText("Low risk")).toBeInTheDocument();
  });
  it("sends filters and search to the API", async () => {
    const spy = vi.spyOn(api, "listAnalyses").mockResolvedValue(page([item(1)]));
    renderAt(<HistoryPage />);
    await screen.findByText("Role 1");
    await userEvent.selectOptions(screen.getByLabelText(/risk level/i), "high");
    await waitFor(() => expect(spy.mock.calls.at(-1)[0]).toMatchObject({ risk_level: "high", page: 1 }));
    await userEvent.type(screen.getByLabelText(/search company/i), "acme");
    await waitFor(() => expect(spy.mock.calls.at(-1)[0]).toMatchObject({ q: "acme", risk_level: "high" }), { timeout: 2000 });
  });
  it("paginates", async () => {
    const spy = vi.spyOn(api, "listAnalyses").mockResolvedValue(page([item(1)], { total: 25, total_pages: 3 }));
    renderAt(<HistoryPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Next" }));
    await waitFor(() => expect(spy.mock.calls.at(-1)[0]).toMatchObject({ page: 2 }));
  });
  it("shows empty, filtered-empty and error states", async () => {
    vi.spyOn(api, "listAnalyses").mockResolvedValue(page([], { total: 0 }));
    renderAt(<HistoryPage />);
    expect(await screen.findByText(/no analyses yet/i)).toBeInTheDocument();
    renderAt(<HistoryPage />, { path: "/", route: "/?q=zzz" });
    expect(await screen.findByText(/no analyses match/i)).toBeInTheDocument();
  });
  it("shows an error with retry", async () => {
    vi.spyOn(api, "listAnalyses").mockRejectedValue(new ApiError(0, "network_error", "Could not reach the server."));
    renderAt(<HistoryPage />);
    expect(await screen.findByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
  it("is accessible", async () => {
    vi.spyOn(api, "listAnalyses").mockResolvedValue(page([item(1)]));
    const { container } = renderAt(<HistoryPage />);
    await screen.findByText("Role 1");
    expect(await a11yViolations(container)).toEqual([]);
  });
});

describe("DashboardPage", () => {
  it("shows an empty state with a call to action when there is no data", async () => {
    vi.spyOn(api, "dashboard").mockResolvedValue({ total_analyses: 0, completed: 0, failed: 0, risk_distribution: { low: 0, medium: 0, high: 0 }, average_risk_score: null, recent: [] });
    renderAt(<DashboardPage />);
    expect(await screen.findByText(/nothing to summarise yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /first posting/i })).toHaveAttribute("href", "/analyze");
  });
  it("renders only the numbers the API returned", async () => {
    vi.spyOn(api, "dashboard").mockResolvedValue({ total_analyses: 4, completed: 3, failed: 1, risk_distribution: { low: 1, medium: 0, high: 2 }, average_risk_score: 41.5, recent: [item(1)] });
    const { container } = renderAt(<DashboardPage />);
    expect(await screen.findByText("41.5")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /2 high, 0 medium, 1 low/ })).toBeInTheDocument();
    expect(await a11yViolations(container)).toEqual([]);
  });
  it("shows an error state", async () => {
    vi.spyOn(api, "dashboard").mockRejectedValue(new ApiError(500, "internal_error", "Boom"));
    renderAt(<DashboardPage />);
    expect(await screen.findByText("Boom")).toBeInTheDocument();
  });
});

describe("LandingPage", () => {
  it("labels sample data and has no invented social proof", async () => {
    const { container } = renderAt(<LandingPage />);
    expect(screen.getByText(/invented text/i)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/testimonial|trusted by|\d+%\s*accura|users protected/i);
    expect(await a11yViolations(container)).toEqual([]);
  });
});
