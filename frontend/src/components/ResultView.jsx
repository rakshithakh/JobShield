import { COMPANY_STATUS, INPUT_TYPE, PATH_NAME, PATH_STATUS, SOURCE_NAME, formatDateTime } from "../lib/format";
import { Alert, RiskBadge, ScoreGauge } from "./ui";

/** Offsets come from Python (code points); JS strings are UTF-16, so slice by code point to stay aligned with emoji. */
export function Highlighted({ text, start, end }) {
  if (start == null || end == null) return <mark className="evidence">{text}</mark>;
  const cp = Array.from(text);
  return <>{cp.slice(0, start).join("")}<mark className="evidence">{cp.slice(start, end).join("")}</mark>{cp.slice(end).join("")}</>;
}

function SignalItem({ s }) {
  return (
    <li className="py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-sans text-base font-semibold">{s.title}</h3>
        <p className="text-sm font-semibold tabular-nums">{s.points > 0 ? `+${s.points} points` : "No points"} <span className="font-normal text-muted">· {SOURCE_NAME[s.source] || s.source}</span></p>
      </div>
      <p className="mt-1 text-ink-soft">{s.explanation}</p>
      {s.evidence && (
        <figure className="mt-2">
          <figcaption className="text-xs font-semibold text-muted">Matched text</figcaption>
          <blockquote className="mt-0.5 border-l-4 border-line-strong bg-note-bg px-3 py-2 text-sm break-words">
            <Highlighted text={s.evidence} start={s.evidence_start} end={s.evidence_end} />
          </blockquote>
        </figure>
      )}
    </li>
  );
}

export default function ResultView({ a }) {
  const failed = a.status === "failed";
  const warnings = a.signals.filter((s) => s.points > 0).sort((x, y) => y.points - x.points);
  const notes = a.signals.filter((s) => s.points === 0);
  const visibleDetectionPaths = a.detection_paths.filter(
    (p) => p.name !== "company_search" && !(p.name === "distilbert" && p.status === "not_configured"),
  );
  const b = a.score_breakdown || {};
  const company = COMPANY_STATUS[a.company_status] || COMPANY_STATUS.unknown;

  if (failed && a.error_code === "not_job_posting") {
    return (
      <Alert tone="info" title="Unable to assess this page">
        No job posting was detected, so no scam-risk score was assigned. Paste the job description or submit a direct job-listing link.
      </Alert>
    );
  }

  if (failed) {
    return (
      <Alert title="This analysis did not complete">
        It was recorded as failed ({a.error_code || "unknown reason"}). Nothing here is a verdict on the posting. Try again, or paste the text instead of using a link.
      </Alert>
    );
  }
  return (
    <div className="space-y-10">
      <section aria-labelledby="score-h" className="space-y-4">
        <h2 id="score-h" className="sr-only">Risk score</h2>
        <ScoreGauge score={a.risk_score} level={a.risk_level} />
        <p className="max-w-2xl text-sm text-muted">This number adds up warning signals found in the text. It is not a probability that the job is a scam, and a low score does not make a posting safe.</p>
      </section>

      <section aria-labelledby="signals-h">
        <h2 id="signals-h" className="text-2xl">Why this score</h2>
        {warnings.length === 0
          ? <p className="mt-3 text-ink-soft">No warning signals matched. That only means these checks found nothing; keep verifying the employer yourself.</p>
          : <ul className="mt-2 divide-y divide-line border-y border-line">{warnings.map((s) => <SignalItem key={s.code} s={s} />)}</ul>}
        {notes.length > 0 && (
          <details className="mt-4">
            <summary className="cursor-pointer text-sm font-semibold">Other observations ({notes.length}), not scored</summary>
            <ul className="mt-2 divide-y divide-line border-y border-line">{notes.map((s) => <SignalItem key={s.code} s={s} />)}</ul>
          </details>
        )}
        <div className="mt-6 overflow-x-auto">
          <table className="w-full min-w-[22rem] text-left text-sm">
            <caption className="pb-2 text-left font-semibold">How the points add up</caption>
            <thead className="text-muted"><tr><th scope="col" className="py-1 pr-4 font-medium">Part</th><th scope="col" className="py-1 text-right font-medium">Points</th></tr></thead>
            <tbody className="divide-y divide-line">
              {[["Rule patterns (capped at 70)", b.rules], ["Text model", b.ml], ["Contact", b.contact], ["Salary", b.salary], ["Company", b.company]].map(([k, v]) => (
                <tr key={k}><th scope="row" className="py-1.5 pr-4 font-normal">{k}</th><td className="py-1.5 text-right tabular-nums">{v ?? 0}</td></tr>))}
              <tr className="font-semibold"><th scope="row" className="py-1.5 pr-4">Total (capped at 100)</th><td className="py-1.5 text-right tabular-nums">{b.raw_total ?? a.risk_score}{b.raw_total > 100 ? ` → ${a.risk_score}` : ""}</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="company-h">
        <h2 id="company-h" className="text-2xl">Company check</h2>
        <p className="mt-2 font-semibold">{a.company_name ? `${a.company_name}: ` : ""}{company}</p>
        <p className="mt-1 max-w-2xl text-sm text-muted">This looks at whether the employer exists, separately from the posting text. Only positive warning evidence adds points; a company that cannot be verified adds none and is not treated as fraudulent.</p>
        <ul className="mt-3 divide-y divide-line border-y border-line">
          {a.company_checks.filter((c) => c.provider !== "company_search").map((c, i) => (
            <li key={i} className="py-3 text-sm">
              <p className="font-semibold">{{ trusted_list: "Known-employer list", name_heuristic: "Name pattern", mca21: "MCA21 registry", company_search: "Online company search", gemini_search: "Legacy web search result", adzuna_listing: "Job-board listing (Adzuna)" }[c.provider] || c.provider}</p>
              <p className="text-ink-soft">{c.summary}</p>
              {c.source_url && <a href={c.source_url} className="underline" rel="noopener noreferrer nofollow" target="_blank">Source</a>}
            </li>))}
          {a.company_checks.length === 0 && <li className="py-3 text-sm text-ink-soft">No company checks were recorded.</li>}
        </ul>
      </section>

      <section aria-labelledby="next-h">
        <h2 id="next-h" className="text-2xl">What to do next</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-ink-soft">{a.recommendations.map((r, i) => <li key={i}>{r}</li>)}</ul>
      </section>

      <section aria-labelledby="how-h">
        <h2 id="how-h" className="text-2xl">How this was analysed</h2>
        <dl className="mt-3 grid gap-x-8 gap-y-1 text-sm sm:grid-cols-2">
          <div className="flex justify-between gap-4 border-b border-line py-1.5"><dt className="text-muted">Analysed</dt><dd>{formatDateTime(a.created_at)}</dd></div>
          <div className="flex justify-between gap-4 border-b border-line py-1.5"><dt className="text-muted">Input</dt><dd>{INPUT_TYPE[a.input_type]}{a.input_truncated ? " (truncated)" : ""}</dd></div>
          <div className="flex justify-between gap-4 border-b border-line py-1.5"><dt className="text-muted">Rules / scoring</dt><dd>{a.versions.rules} / {a.versions.scoring}</dd></div>
          <div className="flex justify-between gap-4 border-b border-line py-1.5"><dt className="text-muted">Text model</dt><dd>{a.versions.model || "not used"}{a.ml_probability != null ? ` (score ${a.ml_probability.toFixed(2)}, not a probability)` : ""}</dd></div>
          {a.source_url && <div className="flex justify-between gap-4 border-b border-line py-1.5 sm:col-span-2"><dt className="text-muted">Page</dt><dd className="break-all">{a.source_url}</dd></div>}
          {a.processing_ms != null && <div className="flex justify-between gap-4 border-b border-line py-1.5"><dt className="text-muted">Processing time</dt><dd>{a.processing_ms} ms</dd></div>}
        </dl>
        <table className="mt-4 w-full text-left text-sm">
          <caption className="pb-2 text-left font-semibold">Checks that ran</caption>
          <tbody className="divide-y divide-line border-y border-line">
            {visibleDetectionPaths.map((p, i) => (
              <tr key={i}><th scope="row" className="py-2 pr-3 font-normal">{PATH_NAME[p.name] || p.name}</th>
                <td className="py-2 pr-3 font-semibold">{PATH_STATUS[p.status] || p.status}</td><td className="py-2 text-muted">{p.detail}</td></tr>))}
          </tbody>
        </table>
      </section>

      <section aria-labelledby="limits-h" className="rounded-md bg-note-bg p-4">
        <h2 id="limits-h" className="text-lg">Limits of this analysis</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-soft">{a.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
      </section>
    </div>
  );
}

export function ResultHeader({ a }) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3"><h1 className="text-3xl sm:text-4xl">{a.job_title || "Job posting analysis"}</h1><RiskBadge level={a.risk_level} status={a.status} errorCode={a.error_code} /></div>
      <p className="text-muted">{a.company_name || "Company not given"} · {formatDateTime(a.created_at)}</p>
    </div>
  );
}
