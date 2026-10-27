import { Link } from "react-router-dom";
import { Fragment } from "react";
import { SAMPLE_PARTS, SAMPLE_SIGNALS, SAMPLE_TOTAL } from "../lib/sample";

const cta = "inline-flex min-h-12 items-center rounded-md bg-brand px-6 text-base font-semibold text-white hover:bg-brand-hover";

export default function DemoPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-10">
      <header className="space-y-3">
        <p className="text-sm font-semibold uppercase tracking-wide text-muted">Product demo</p>
        <h1 className="text-4xl sm:text-5xl">See how a posting is analysed</h1>
        <p className="max-w-3xl text-lg text-ink-soft">This walkthrough uses invented job-posting text and the rule engine’s sample output. It does not contact external services or create an analysis in your history.</p>
      </header>

      <section className="grid gap-8 md:grid-cols-[1.1fr_0.9fr]" aria-label="Sample analysis walkthrough">
        <article className="rounded-md border border-line-strong bg-surface p-6">
          <h2 className="text-2xl">1. Add a posting</h2>
          <p className="mt-2 text-sm text-muted">Example text with warning phrases highlighted</p>
          <blockquote className="mt-4 text-lg leading-8">
            {SAMPLE_PARTS.map((p, i) => <Fragment key={i}>{p.m ? <mark className="evidence">{p.t}</mark> : p.t}</Fragment>)}
          </blockquote>
        </article>

        <article className="rounded-md border border-line-strong bg-surface p-6">
          <h2 className="text-2xl">2. Review the signals</h2>
          <ul className="mt-4 divide-y divide-line border-y border-line">
            {SAMPLE_SIGNALS.map((s) => (
              <li key={s.key} className="flex justify-between gap-4 py-3">
                <span>{s.title}</span><strong className="shrink-0">+{s.points}</strong>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-sm text-ink-soft">Each warning shows what matched and how many points it added. Rule points have a cap; several independent checks can contribute.</p>
        </article>
      </section>

      <section className="rounded-md bg-note-bg p-6 sm:p-8" aria-labelledby="demo-score">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 id="demo-score" className="text-2xl">3. Understand the score</h2>
            <p className="mt-2 text-ink-soft">Sample score: {SAMPLE_TOTAL.raw} warning points before the 100-point cap.</p>
          </div>
          <p className="font-serif text-5xl font-semibold">{SAMPLE_TOTAL.capped}<span className="ml-2 text-xl font-normal text-muted">/ 100</span></p>
        </div>
        <p className="mt-4 max-w-3xl text-ink-soft">The score counts warning signals; it is not a probability or proof that a job is a scam. A real analysis also checks contact details, salary, available company information and text-model patterns. Unavailable checks are reported separately and do not count as evidence against a company.</p>
      </section>

      <section className="flex flex-wrap items-center justify-between gap-5 border-t border-line pt-8">
        <div>
          <h2 className="text-2xl">Ready to analyse your own posting?</h2>
          <p className="mt-1 text-ink-soft">Paste the text, enter a public link, or upload a PDF or text file.</p>
        </div>
        <Link to="/analyze" className={cta}>Analyse a job posting</Link>
      </section>
    </div>
  );
}
