import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { EmptyState, ErrorState, LoadingBlock } from "../components/ui";
import { AnalysisRow } from "./HistoryPage";
import { RISK } from "../lib/format";

const SEG = { high: "bg-risk-high", medium: "bg-risk-med", low: "bg-risk-low" };

export default function DashboardPage() {
  const { data, error, loading, reload } = useAsync((s) => api.dashboard(s), []);
  if (loading) return <LoadingBlock label="Loading dashboard" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (data.total_analyses === 0) return (
    <div className="space-y-6"><h1 className="text-4xl">Dashboard</h1>
      <EmptyState title="Nothing to summarise yet" action={<Link to="/analyze" className="inline-flex min-h-11 items-center rounded-md bg-brand px-4 text-sm font-semibold text-white hover:bg-brand-hover">Analyse your first posting</Link>}>
        This page summarises analyses made from this browser. Run one to see your totals.</EmptyState></div>);
  const d = data.risk_distribution, done = data.completed;
  return (
    <div className="space-y-10">
      <h1 className="text-4xl">Dashboard</h1>
      <dl className="grid grid-cols-2 gap-6 sm:grid-cols-4">
        {[["Analyses", data.total_analyses], ["Completed", data.completed], ["Failed", data.failed], ["Average score", data.average_risk_score ?? "n/a"]].map(([k, v]) => (
          <div key={k} className="border-t-2 border-ink pt-2"><dt className="text-sm text-muted">{k}</dt><dd className="font-serif text-4xl tabular-nums">{v}</dd></div>))}
      </dl>
      <section aria-labelledby="dist-h">
        <h2 id="dist-h" className="text-2xl">Risk levels</h2>
        {done === 0 ? <p className="mt-2 text-muted">No completed analyses yet.</p> : (
          <>
            <div className="mt-3 flex h-4 overflow-hidden rounded-full border border-line-strong" role="img" aria-label={`Risk levels: ${d.high} high, ${d.medium} medium, ${d.low} low`}>
              {["high", "medium", "low"].map((k) => d[k] > 0 && <div key={k} className={SEG[k]} style={{ width: `${(d[k] / done) * 100}%` }} />)}
            </div>
            <ul className="mt-3 flex flex-wrap gap-x-8 gap-y-1 text-sm">
              {["high", "medium", "low"].map((k) => (
                <li key={k}><Link className="underline-offset-2 hover:underline" to={`/history?risk_level=${k}`}><span className="font-semibold tabular-nums">{d[k]}</span> {RISK[k].label.toLowerCase()}</Link></li>))}
            </ul>
          </>)}
      </section>
      <section aria-labelledby="recent-h">
        <div className="flex items-baseline justify-between"><h2 id="recent-h" className="text-2xl">Recent analyses</h2><Link to="/history" className="text-sm font-semibold underline">View all</Link></div>
        <ul className="mt-2 divide-y divide-line border-y border-line">{data.recent.map((a) => <AnalysisRow key={a.id} a={a} />)}</ul>
      </section>
    </div>
  );
}
