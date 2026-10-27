import { Link } from "react-router-dom";
import { Fragment } from "react";
import { SAMPLE_PARTS, SAMPLE_SIGNALS, SAMPLE_TOTAL } from "../lib/sample";

const cta = "inline-flex min-h-12 items-center rounded-md bg-brand px-6 text-base font-semibold text-white hover:bg-brand-hover";
const STEPS = [
  ["Add the posting", "Paste the message, give a link to a public page, or upload a PDF or text file."],
  ["Checks run", "Pattern rules, contact and salary checks, a company check and a text model each look at it."],
  ["See the evidence", "Every warning signal shows the text that triggered it and the points it added."],
  ["Verify yourself", "You get steps for confirming the employer through channels the posting does not control."],
];
const CHECKS = [
  ["Money asked of you", "Registration, training, kit or deposit payments, including reworded versions."],
  ["Pressure and promises", "Countdown seats, guaranteed income, no requirements at all."],
  ["Payment and contact pattern", "Daily wallet payouts, pay-per-entry work, Telegram or WhatsApp-only contact."],
  ["Recruitment-for-income schemes", "Network marketing and pyramid structures dressed up as jobs."],
  ["Who is contacting you", "Free-mail addresses, and big-company names paired with them."],
  ["Does the pay add up", "Salary compared with real advertised pay for the role where available, otherwise rough estimates (labelled)."],
  ["Does the company exist", "Known-employer list and job-board listing check. Verify the employer independently on its official website or the MCA portal."],
  ["Wording similarity", "A text model trained on a public set of real and fraudulent postings. It carries the most weight but is less proven on Indian-style scams."],
];

export default function LandingPage() {
  return (
    <div className="space-y-24">
      <section className="grid items-start gap-10 lg:grid-cols-[1.05fr_1fr]" aria-labelledby="hero-h">
        <div className="space-y-6">
          <h1 id="hero-h" className="text-5xl sm:text-6xl">Before you reply, see what the posting is really asking of you.</h1>
          <p className="max-w-xl text-lg text-ink-soft">JobSentinel checks a job message for scam warning signs and shows exactly which words, contact details and numbers raised each flag. It points you to what to verify next. It never claims certainty.</p>
          <div className="flex flex-wrap items-center gap-4"><Link to="/analyze" className={cta}>Analyse a job posting</Link><Link to="/demo" className="font-semibold underline underline-offset-4">See the demo</Link><Link to="/about" className="font-semibold underline underline-offset-4">How the score works</Link></div>
        </div>
        <figure className="rounded-md border border-line-strong bg-surface p-5" aria-labelledby="sample-cap">
          <figcaption id="sample-cap" className="mb-3 text-sm font-semibold text-muted">Sample posting (invented text, shown to illustrate the output)</figcaption>
          <blockquote className="text-lg leading-8">
            {SAMPLE_PARTS.map((p, i) => <Fragment key={i}>{p.m ? <mark className="evidence">{p.t}</mark> : p.t}</Fragment>)}
          </blockquote>
          <table className="mt-5 w-full text-sm">
            <caption className="sr-only">Signals found in the sample</caption>
            <tbody className="divide-y divide-line border-y border-line">
              {SAMPLE_SIGNALS.map((s) => <tr key={s.key}><th scope="row" className="py-1.5 pr-2 text-left font-normal">{s.title}</th><td className="py-1.5 text-right font-semibold tabular-nums">+{s.points}</td></tr>)}
              <tr><th scope="row" className="py-1.5 pr-2 text-left font-semibold">Total, capped at 100</th><td className="py-1.5 text-right font-semibold tabular-nums">{SAMPLE_TOTAL.raw} → {SAMPLE_TOTAL.capped}</td></tr>
            </tbody>
          </table>
          <p className="mt-3 text-xs text-muted">Real output of the rule engine on this text. Live analyses also include the text model and company checks.</p>
        </figure>
      </section>

      <section aria-labelledby="how-h" className="space-y-6">
        <h2 id="how-h" className="text-3xl">How an analysis works</h2>
        <ol className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map(([t, d], i) => <li key={t} className="border-t-2 border-ink pt-3"><p className="text-sm font-semibold text-muted">Step {i + 1}</p><h3 className="mt-1 font-sans text-lg font-semibold">{t}</h3><p className="mt-1 text-ink-soft">{d}</p></li>)}
        </ol>
      </section>

      <section aria-labelledby="checks-h" className="space-y-6">
        <h2 id="checks-h" className="text-3xl">What it looks for</h2>
        <dl className="grid gap-x-10 gap-y-5 sm:grid-cols-2">
          {CHECKS.map(([t, d]) => <div key={t}><dt className="font-semibold">{t}</dt><dd className="text-ink-soft">{d}</dd></div>)}
        </dl>
      </section>

      <section aria-labelledby="trust-h" className="grid gap-10 rounded-md bg-note-bg p-6 sm:p-10 lg:grid-cols-2">
        <div id="privacy"><h2 id="trust-h" className="text-3xl">Privacy</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-ink-soft">
            <li>No account. Your history is tied to a random token kept in this browser.</li>
            <li>By default the text you submit is not stored. We keep the result, short matched excerpts and a hash.</li>
            <li>You can delete any analysis from its page.</li>
          </ul></div>
        <div id="limits"><h2 className="text-3xl">Limits</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-ink-soft">
            <li>A low score is not a guarantee. A high score is not proof.</li>
            <li>An unverified company is reported as unknown, never as fraudulent.</li>
            <li>Rules are tuned to English and Indian-context scams and can miss new wording.</li>
          </ul></div>
      </section>

      <section className="flex flex-wrap items-center justify-between gap-4 border-t border-line pt-8">
        <h2 className="text-3xl">Got a message you are unsure about?</h2><Link to="/analyze" className={cta}>Analyse a job posting</Link>
      </section>
    </div>
  );
}
