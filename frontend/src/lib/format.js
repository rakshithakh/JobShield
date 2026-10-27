export const RISK = {
  low: { label: "Low risk", note: "Few warning signals found" },
  medium: { label: "Medium risk", note: "Some warning signals found" },
  high: { label: "High risk", note: "Many warning signals found" },
};

export const COMPANY_STATUS = {
  known_employer: "Name matches a well-known employer",
  registry_active: "Found in the company registry",
  registry_inactive: "Registry lists it as struck off or dissolved",
  registry_not_found: "Not found in registry (inconclusive)",
  name_heuristic: "Name resembles generic job-scheme naming (weak signal)",
  not_provided: "No company name given",
  not_configured: "Registry lookup is not configured",
  unavailable: "Could not be checked right now",
  unknown: "Unknown: could not be verified",
  listing_found: "A matching job-board listing exists (information only)",
  listing_not_found: "No matching job-board listing (inconclusive)",
};

export const PATH_STATUS = { ok: "Worked", failed: "Failed", unavailable: "Unavailable", not_configured: "Not configured", skipped: "Skipped" };
export const PATH_NAME = { rules: "Rule patterns", contact: "Contact check", salary: "Salary check", tfidf: "Text model (TF-IDF)", distilbert: "Text model (DistilBERT)", mca21: "MCA21 company registry", company_search: "Online company search", adzuna: "Job-board listing check (Adzuna)", adzuna_salary: "Salary benchmark (Adzuna)" };
export const INPUT_TYPE = { text: "Pasted text", url: "Web page", file: "Uploaded file" };
export const SOURCE_NAME = { rules: "Rule patterns", contact: "Contact", salary: "Salary", company: "Company", ml: "Text model" };

export function formatDateTime(iso) {
  if (!iso) return "";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
}
