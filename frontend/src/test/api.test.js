import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, getSessionToken } from "../lib/api";

const ok = (body, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
afterEach(() => vi.restoreAllMocks());

describe("api client", () => {
  it("creates a stable URL-safe session token and sends it", async () => {
    const t = getSessionToken();
    expect(t).toMatch(/^[A-Za-z0-9_-]{32,128}$/);
    expect(getSessionToken()).toBe(t);
    const f = vi.spyOn(globalThis, "fetch").mockImplementation(() => ok({ items: [] }));
    await api.listAnalyses({ q: "acme", risk_level: "", page: 2 });
    const [url, init] = f.mock.calls[0];
    expect(init.headers["X-Session-Token"]).toBe(t);
    expect(String(url)).toContain("q=acme");
    expect(String(url)).toContain("page=2");
    expect(String(url)).not.toContain("risk_level");
  });
  it("turns structured server errors into ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => ok({ error: { code: "url_not_allowed", message: "Nope", request_id: "abc" } }, 422));
    await expect(api.createAnalysis({ job_url: "http://x" })).rejects.toMatchObject({ status: 422, code: "url_not_allowed", message: "Nope", requestId: "abc" });
  });
  it("handles non-JSON error bodies and network failure", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementationOnce(() => Promise.resolve(new Response("<html>bad gateway</html>", { status: 502 })));
    await expect(api.dashboard()).rejects.toBeInstanceOf(ApiError);
    vi.spyOn(globalThis, "fetch").mockImplementationOnce(() => Promise.reject(new TypeError("fail")));
    await expect(api.dashboard()).rejects.toMatchObject({ code: "network_error" });
  });
  it("returns null for 204", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.resolve(new Response(null, { status: 204 })));
    expect(await api.deleteAnalysis("x")).toBeNull();
  });
});
