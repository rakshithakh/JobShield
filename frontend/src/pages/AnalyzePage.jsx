import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, Globe, ClipboardPaste } from "lucide-react";
import { api } from "../lib/api";
import { Alert, Button, Field, cx, inputCls, useToast } from "../components/ui";

const MODES = [["text", "Paste text", ClipboardPaste], ["url", "Web page link", Globe], ["file", "Upload file", FileText]];
const MAX_FILE = 5 * 1024 * 1024;

export function validate(mode, v) {
  const e = {};
  if (mode === "text") {
    const t = v.text.trim();
    if (t.length < 20) e.text = "Paste at least 20 characters of the job description or message.";
    else if (t.length > 20000) e.text = "That is over the 20,000 character limit. Paste the key part of the posting.";
  }
  if (mode === "url") {
    try {
      const u = new URL(v.url.trim());
      if (!["http:", "https:"].includes(u.protocol)) throw new Error();
    } catch { e.url = "Enter a full web address starting with http:// or https://"; }
  }
  if (mode === "file") {
    if (!v.file) e.file = "Choose a PDF or .txt file.";
    else if (!/\.(pdf|txt)$/i.test(v.file.name)) e.file = "Only PDF and .txt files are supported.";
    else if (v.file.size > MAX_FILE) e.file = "The file is larger than 5 MB.";
  }
  if (v.company.length > 200) e.company = "Keep the company name under 200 characters.";
  if (v.title.length > 200) e.title = "Keep the job title under 200 characters.";
  return e;
}

export default function AnalyzePage() {
  const nav = useNavigate();
  const toast = useToast();
  const [mode, setMode] = useState("text");
  const [v, setV] = useState({ text: "", url: "", file: null, company: "", title: "" });
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [apiError, setApiError] = useState(null);
  const inflight = useRef(false);
  const set = (k) => (e) => setV((s) => ({ ...s, [k]: e.target.value }));
  const urlFetchFailed = mode === "url" && apiError?.code === "url_fetch_failed";

  function switchToPasteText() {
    setMode("text");
    setErrors({});
    setApiError(null);
  }

  async function submit(e) {
    e?.preventDefault();
    if (inflight.current) return;                      // guards against double clicks / double Enter
    const errs = validate(mode, v);
    setErrors(errs); setApiError(null);
    if (Object.keys(errs).length) return;
    inflight.current = true; setSubmitting(true);
    try {
      const common = { job_title: v.title.trim() || undefined, company_name: v.company.trim() || undefined };
      const res = mode === "file"
        ? await api.uploadAnalysis({ file: v.file, jobTitle: common.job_title, companyName: common.company_name })
        : await api.createAnalysis({ ...common, ...(mode === "text" ? { job_text: v.text.trim() } : { job_url: v.url.trim() }) });
      toast.push("Analysis saved to your history.");
      nav(`/analyses/${res.id}`);
    } catch (err) {
      if (err.status === 422 && Array.isArray(err.details)) {
        const map = { job_text: "text", job_url: "url", company_name: "company", job_title: "title" };
        setErrors(Object.fromEntries(err.details.map((d) => [map[d.field] || "form", d.message])));
      }
      setApiError(err);
    } finally { inflight.current = false; setSubmitting(false); }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-4xl">Analyse a job posting</h1>
      <p className="mt-3 text-ink-soft">Add the posting however you received it. The more of the original message you include, the more the checks can see.</p>
      <form onSubmit={submit} noValidate className="mt-8 space-y-6" aria-describedby={apiError ? "form-error" : undefined}>
        <fieldset>
          <legend className="mb-2 text-sm font-semibold">How do you want to add it?</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {MODES.map(([k, label, Icon]) => (
              <label key={k} className={cx("flex min-h-11 cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus", mode === k ? "border-brand bg-note-bg" : "border-line-strong bg-surface")}>
                <input type="radio" name="mode" value={k} checked={mode === k} onChange={() => { setMode(k); setErrors({}); setApiError(null); }} className="sr-only" />
                <Icon className="size-4" aria-hidden="true" />{label}
              </label>))}
          </div>
        </fieldset>

        {mode === "text" && (
          <Field label="Job description or message" error={errors.text} hint="Include contact details and pay terms if the message has them.">
            {(p) => <textarea {...p} rows={10} value={v.text} onChange={set("text")} className={inputCls} placeholder="Paste the job description, WhatsApp message or offer letter text" />}
          </Field>)}
        {mode === "url" && (
          <Field label="Link to the job posting" error={errors.url} hint="We fetch the public page. Pages that need login or JavaScript usually cannot be read; paste the text instead.">
            {(p) => <input {...p} type="url" inputMode="url" value={v.url} onChange={set("url")} className={inputCls} placeholder="https://example.com/jobs/123" />}
          </Field>)}
        {mode === "file" && (
          <Field label="Offer letter or job description" error={errors.file} hint="PDF or .txt, up to 5 MB. Scanned images are not supported.">
            {(p) => <input {...p} type="file" accept=".pdf,.txt,application/pdf,text/plain" onChange={(e) => setV((s) => ({ ...s, file: e.target.files?.[0] || null }))} className={cx(inputCls, "file:mr-3 file:rounded file:border-0 file:bg-note-bg file:px-3 file:py-1.5 file:font-semibold")} />}
          </Field>)}

        <div className="grid gap-6 sm:grid-cols-2">
          <Field label="Company name" optional error={errors.company} hint="Used for the company check.">{(p) => <input {...p} value={v.company} onChange={set("company")} className={inputCls} autoComplete="off" />}</Field>
          <Field label="Job title" optional error={errors.title}>{(p) => <input {...p} value={v.title} onChange={set("title")} className={inputCls} autoComplete="off" />}</Field>
        </div>

        {apiError && (
          <div id="form-error"><Alert title={urlFetchFailed ? "The page could not be read automatically" : "The analysis could not be completed"} action={<div className="flex flex-wrap gap-2"><Button type="button" variant="secondary" onClick={submit}>Try again</Button>{urlFetchFailed && <Button type="button" variant="secondary" onClick={switchToPasteText}>Paste job text instead</Button>}</div>}>
            <p>{urlFetchFailed ? "No score was assigned. Open the posting in your browser, copy its job title and description, then paste them here. Some sites block automated access." : apiError.message}</p>{apiError.requestId && <p className="text-muted">Reference: {apiError.requestId}</p>}
            {apiError.analysisId && <p><a className="underline" href={`/analyses/${apiError.analysisId}`}>See the failed record</a></p>}
          </Alert></div>)}

        <div className="flex flex-wrap items-center gap-4">
          <Button type="submit" loading={submitting} className="min-w-44">{submitting ? "Analysing…" : "Analyse posting"}</Button>
          <p className="text-sm text-muted" aria-live="polite">{submitting ? "This usually takes a few seconds." : "Your text is not kept after analysis unless the server is configured to retain it."}</p>
        </div>
      </form>
    </div>
  );
}
