import { useEffect } from "react";
import { useLocation } from "react-router-dom";

export default function AboutPage() {
  const { hash } = useLocation();
  useEffect(() => { if (hash) document.getElementById(hash.slice(1))?.scrollIntoView(); }, [hash]);
  return (
    <div className="mx-auto max-w-3xl space-y-12">
      <h1 className="text-4xl">How JobSentinel works</h1>
      <section id="scoring" className="space-y-3" aria-labelledby="scoring-h">
        <h2 id="scoring-h" className="text-3xl">How scoring works</h2>
        <p className="text-ink-soft">The score is a heuristic total of warning signals, from 0 to 100. It is not a calibrated probability of fraud. Only warning evidence adds points; nothing subtracts, so a clean result means &ldquo;few signals found&rdquo;, not &ldquo;safe&rdquo;.</p>
        <ul className="list-disc space-y-2 pl-5 text-ink-soft">
          <li><strong>Rule patterns</strong>: six groups (fees, urgency, unrealistic promises, work/payment pattern, network marketing, too-good-to-be-true). Each group counts once; the rule total is capped at 70.</li>
          <li><strong>Contact</strong>: a free-mail address adds 25 once. If the company name matches a known employer, the same warning shows stronger context but does not add the email points again. An explicit Gmail contact instruction without an address adds a weaker 10-point warning.</li>
          <li><strong>Salary</strong>: far above the typical range for the role adds 30, above adds 15, far below adds 8. The range comes from real advertised salaries (Adzuna) when that lookup is configured and has enough listings; otherwise from a rough, unsourced table, and the result says which.</li>
          <li><strong>Company</strong>: a weak name-pattern match adds 15. Online company search is disabled. Unknown or unverifiable adds nothing. A job-board listing is information only; scammers can copy real listings. Verify employers on their official website or the MCA portal.</li>
          <li><strong>Text model</strong>: up to 40 points, ramping from a model score of 0.5 (none) to 0.9 (full). It is a TF-IDF classifier trained on the public EMSCAD dataset, which is mostly US/UK English postings, so it is less proven on Indian WhatsApp or UPI-style scams. Its score is not a probability.</li>
        </ul>
        <p className="text-ink-soft">Levels: 60 and above is high, 35 to 59 is medium, below 35 is low.</p>
      </section>
      <section id="privacy" className="space-y-3" aria-labelledby="privacy-h">
        <h2 id="privacy-h" className="text-3xl">Privacy</h2>
        <p className="text-ink-soft">There are no accounts. Your browser keeps a random token that scopes your history on the server. Clear your browser data and that history can no longer be reached from this browser. By default the submitted text is not stored; results, short matched excerpts, a content hash and metadata are. If a server operator turns on retention, the text is kept for a limited number of days and then removed. Web page links are fetched by the server, which refuses private and internal addresses.</p>
      </section>
      <section id="limits" className="space-y-3" aria-labelledby="limits-h">
        <h2 id="limits-h" className="text-3xl">Limitations</h2>
        <ul className="list-disc space-y-2 pl-5 text-ink-soft">
          <li>Automated analysis aids your judgement. It cannot prove that a company or posting is fraudulent or genuine.</li>
          <li>Pattern rules can miss reworded scams and can flag unusual but honest wording.</li>
          <li>Company lookups can be unavailable or inconclusive. That is shown as such.</li>
          <li>Many job sites need login or JavaScript, so their links cannot be read. Paste the text instead.</li>
        </ul>
        <p className="text-ink-soft">If you have lost money or shared sensitive data, in India you can report at cybercrime.gov.in or call 1930.</p>
      </section>
    </div>
  );
}
