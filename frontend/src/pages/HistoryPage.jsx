import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { Button, EmptyState, ErrorState, LoadingBlock, Pagination, RiskBadge, inputCls } from "../components/ui";
import { INPUT_TYPE, formatDateTime } from "../lib/format";

const PAGE_SIZE = 10;

export function AnalysisRow({ a }) {
  return (
    <li>
      <Link to={`/analyses/${a.id}`} className="grid gap-x-4 gap-y-1 px-2 py-3 hover:bg-note-bg sm:grid-cols-[1fr_auto] sm:items-center">
        <span className="min-w-0">
          <span className="block truncate font-semibold">{a.job_title || "Untitled posting"}</span>
          <span className="block truncate text-sm text-muted">{a.company_name || "Company not given"} · {INPUT_TYPE[a.input_type]} · {formatDateTime(a.created_at)}</span>
        </span>
        <span className="flex items-center gap-3">
          {a.risk_score != null && <span className="text-sm tabular-nums text-ink-soft">Score {a.risk_score}</span>}
          <RiskBadge level={a.risk_level} status={a.status} errorCode={a.error_code} />
        </span>
      </Link>
    </li>
  );
}

export default function HistoryPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") || "", risk = params.get("risk_level") || "", status = params.get("status") || "";
  const sort = params.get("sort") || "newest", page = Number(params.get("page") || 1);
  const [search, setSearch] = useState(q);

  const update = (patch) => setParams((p) => {
    const n = new URLSearchParams(p);
    Object.entries(patch).forEach(([k, v]) => (v ? n.set(k, v) : n.delete(k)));
    if (!("page" in patch)) n.delete("page");
    return n;
  }, { replace: true });

  useEffect(() => { // debounce search -> URL
    if (search === q) return;
    const h = setTimeout(() => update({ q: search.trim() }), 300);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const { data, error, loading, reload } = useAsync(
    (s) => api.listAnalyses({ q, risk_level: risk, status, sort, page, page_size: PAGE_SIZE }, s), [q, risk, status, sort, page]);
  const filtered = Boolean(q || risk || status);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="text-4xl">History</h1>
        <Link to="/analyze" className="inline-flex min-h-11 items-center rounded-md bg-brand px-4 text-sm font-semibold text-white hover:bg-brand-hover">New analysis</Link>
      </div>
      <form role="search" aria-label="Filter analyses" onSubmit={(e) => e.preventDefault()} className="grid gap-3 sm:grid-cols-[2fr_1fr_1fr_1fr]">
        <div><label htmlFor="q" className="mb-1 block text-sm font-semibold">Search company or title</label>
          <input id="q" type="search" value={search} onChange={(e) => setSearch(e.target.value)} className={inputCls} maxLength={100} /></div>
        <div><label htmlFor="risk" className="mb-1 block text-sm font-semibold">Risk level</label>
          <select id="risk" value={risk} onChange={(e) => update({ risk_level: e.target.value })} className={inputCls}>
            <option value="">All</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></div>
        <div><label htmlFor="status" className="mb-1 block text-sm font-semibold">Status</label>
          <select id="status" value={status} onChange={(e) => update({ status: e.target.value })} className={inputCls}>
            <option value="">All</option><option value="completed">Completed</option><option value="failed">Failed</option></select></div>
        <div><label htmlFor="sort" className="mb-1 block text-sm font-semibold">Sort by</label>
          <select id="sort" value={sort} onChange={(e) => update({ sort: e.target.value === "newest" ? "" : e.target.value })} className={inputCls}>
            <option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="risk_desc">Highest score</option><option value="risk_asc">Lowest score</option></select></div>
      </form>

      <div aria-live="polite">
        {loading && <LoadingBlock label="Loading history" />}
        {error && <ErrorState error={error} onRetry={reload} />}
        {data && data.total === 0 && (filtered
          ? <EmptyState title="No analyses match these filters" action={<Button variant="secondary" onClick={() => { setSearch(""); setParams({}); }}>Clear filters</Button>}>Try a different company name or remove a filter.</EmptyState>
          : <EmptyState title="No analyses yet" action={<Link to="/analyze" className="inline-flex min-h-11 items-center rounded-md bg-brand px-4 text-sm font-semibold text-white">Analyse your first posting</Link>}>Your analyses appear here, saved for this browser.</EmptyState>)}
        {data && data.total > 0 && (
          <>
            <p className="mb-2 text-sm text-muted">{data.total} {data.total === 1 ? "analysis" : "analyses"}</p>
            <ul className="divide-y divide-line border-y border-line">{data.items.map((a) => <AnalysisRow key={a.id} a={a} />)}</ul>
            <Pagination page={data.page} totalPages={data.total_pages} onChange={(p) => update({ page: p > 1 ? String(p) : "" })} />
          </>)}
      </div>
    </div>
  );
}
