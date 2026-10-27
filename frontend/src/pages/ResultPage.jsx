import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { Button, ErrorState, LoadingBlock, useToast } from "../components/ui";
import ResultView, { ResultHeader } from "../components/ResultView";

export default function ResultPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const { data, error, loading, reload } = useAsync((s) => api.getAnalysis(id, s), [id]);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  async function remove() {
    setBusy(true);
    try { await api.deleteAnalysis(id); toast.push("Analysis deleted."); nav("/history"); }
    catch (e) { toast.push(e.message, "error"); setBusy(false); }
  }

  if (loading) return <LoadingBlock label="Loading analysis" />;
  if (error?.status === 404) return (
    <div className="space-y-3"><h1 className="text-3xl">Analysis not found</h1>
      <p className="text-ink-soft">It may have been deleted, or it was created in a different browser. History is tied to the browser you used.</p>
      <Link className="font-semibold underline" to="/history">Go to history</Link></div>);
  if (error) return <ErrorState error={error} onRetry={reload} />;

  return (
    <article className="space-y-8">
      <ResultHeader a={data} />
      <ResultView a={data} />
      <div className="flex flex-wrap items-center gap-3 border-t border-line pt-6">
        <Link to="/analyze" className="inline-flex min-h-11 items-center rounded-md bg-brand px-4 text-sm font-semibold text-white hover:bg-brand-hover">Analyse another posting</Link>
        <Link to="/history" className="inline-flex min-h-11 items-center rounded-md border border-line-strong px-4 text-sm font-semibold hover:bg-note-bg">Back to history</Link>
        {!confirming
          ? <Button variant="ghost" onClick={() => setConfirming(true)}>Delete this analysis</Button>
          : <span role="group" aria-label="Confirm deletion" className="flex items-center gap-2"><span className="text-sm">Delete permanently?</span>
              <Button variant="danger" loading={busy} onClick={remove}>Yes, delete</Button><Button variant="secondary" onClick={() => setConfirming(false)}>Cancel</Button></span>}
      </div>
    </article>
  );
}
