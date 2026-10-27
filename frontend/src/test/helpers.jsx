import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import axe from "axe-core";
import { ToastProvider } from "../components/ui";

export function renderAt(ui, { path = "/", route = "/" } = {}) {
  return render(
    <ToastProvider><MemoryRouter initialEntries={[route]}>
      <Routes><Route path={path} element={ui} /><Route path="*" element={<div>NAVIGATED:{"{"}elsewhere{"}"}</div>} /></Routes>
    </MemoryRouter></ToastProvider>);
}

export async function a11yViolations(container) {
  const r = await axe.run(container, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
  return r.violations.map((v) => `${v.id}: ${v.help}`);
}

// Shaped like the backend's AnalysisDetail response (test fixture only).
export const detail = (over = {}) => ({
  id: "11111111-1111-1111-1111-111111111111", created_at: "2026-10-01T10:00:00Z", status: "completed", input_type: "text",
  job_title: "Data Entry Operator", company_name: "Acme Widgets", risk_score: 72, risk_level: "high", company_status: "unknown",
  error_code: null, source_url: null, input_length: 200, input_truncated: false, input_retained_until: null,
  ml_probability: 0.74, ml_model: "tfidf", versions: { rules: "rules-2", scoring: "scoring-2", model: "tfidf-lr:abcd1234" },
  score_breakdown: { rules: 37, ml: 10, contact: 25, salary: 0, company: 0, raw_total: 72, capped_total: 72 },
  signals: [
    { code: "rule:registration_training_fee", source: "rules", title: "Registration/Training Fee", severity: "high", points: 30, explanation: "Legitimate employers do not ask candidates to pay.", evidence: "Pay Rs 999 registration fee" },
    { code: "contact:none", source: "contact", title: "No contact email in the text", severity: "info", points: 0, explanation: "Not scored.", evidence: null },
  ],
  company_checks: [{ provider: "mca21", status: "not_configured", summary: "MCA21 registry lookup is not configured on this server.", source_url: null }],
  detection_paths: [{ name: "rules", status: "ok", detail: "" }, { name: "mca21", status: "not_configured", detail: "MCA_API_KEY not set" }],
  recommendations: ["Never pay a fee to get a job."], limitations: ["This is an automated aid, not proof."], processing_ms: 12, ...over,
});
