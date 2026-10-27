// Centralised API client. Components never call fetch directly.
function apiBase() {
  return (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");
}
const TOKEN_KEY = "jobsentinel.session";

export class ApiError extends Error {
  constructor(status, code, message, requestId, details, analysisId) {
    super(message);
    this.status = status; this.code = code; this.requestId = requestId; this.details = details; this.analysisId = analysisId;
  }
}

function randomToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** Anonymous per-browser token. It scopes history on the server; it is NOT a login. */
export function getSessionToken() {
  try {
    let t = localStorage.getItem(TOKEN_KEY);
    if (!t || !/^[A-Za-z0-9_-]{32,128}$/.test(t)) {
      t = randomToken();
      localStorage.setItem(TOKEN_KEY, t);
    }
    return t;
  } catch {
    // Storage blocked: fall back to a per-page-load token (history will not persist across reloads).
    window.__jsTok ||= randomToken();
    return window.__jsTok;
  }
}

async function request(path, { method = "GET", json, form, params, signal } = {}) {
  const url = new URL(apiBase() + path, window.location.origin);
  if (params) Object.entries(params).forEach(([k, v]) => v !== undefined && v !== "" && v !== null && url.searchParams.set(k, v));
  const headers = { "X-Session-Token": getSessionToken() };
  let body;
  if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  if (form) body = form;
  let res;
  try {
    res = await fetch(url, { method, headers, body, signal });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ApiError(0, "network_error", "Could not reach the server. Check your connection and try again.");
  }
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON error body */ }
  if (!res.ok) {
    const err = data?.error;
    throw new ApiError(res.status, err?.code || "http_error", err?.message || `The server returned an error (${res.status}).`,
      err?.request_id, err?.details, err?.analysis_id);
  }
  return data;
}

export const api = {
  health: (signal) => request("/api/v1/health", { signal }),
  createAnalysis: (payload) => request("/api/v1/analyses", { method: "POST", json: payload }),
  uploadAnalysis: ({ file, jobTitle, companyName }) => {
    const form = new FormData();
    form.append("file", file);
    if (jobTitle) form.append("job_title", jobTitle);
    if (companyName) form.append("company_name", companyName);
    return request("/api/v1/analyses/upload", { method: "POST", form });
  },
  listAnalyses: (params, signal) => request("/api/v1/analyses", { params, signal }),
  getAnalysis: (id, signal) => request(`/api/v1/analyses/${encodeURIComponent(id)}`, { signal }),
  deleteAnalysis: (id) => request(`/api/v1/analyses/${encodeURIComponent(id)}`, { method: "DELETE" }),
  dashboard: (signal) => request("/api/v1/dashboard/summary", { signal }),
};
