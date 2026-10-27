import { createContext, useCallback, useContext, useEffect, useId, useState } from "react";
import { AlertTriangle, CheckCircle2, OctagonAlert, ShieldCheck, TriangleAlert, Loader2, X, Info } from "lucide-react";
import { RISK } from "../lib/format";

export function cx(...a) { return a.filter(Boolean).join(" "); }

const BTN = {
  primary: "bg-brand text-white hover:bg-brand-hover disabled:bg-line-strong disabled:text-white",
  secondary: "bg-surface text-ink border border-line-strong hover:bg-note-bg disabled:text-muted",
  danger: "bg-surface text-risk-high border border-risk-high hover:bg-risk-high-bg",
  ghost: "text-ink-soft hover:bg-note-bg",
};
export function Button({ variant = "primary", loading = false, className, children, ...rest }) {
  return (
    <button {...rest} disabled={rest.disabled || loading} aria-busy={loading || undefined}
      className={cx("inline-flex min-h-11 items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold transition-colors disabled:cursor-not-allowed", BTN[variant], className)}>
      {loading && <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
      {children}
    </button>
  );
}

export function Field({ label, hint, error, children, optional }) {
  const id = useId();
  const describedBy = [hint && `${id}-hint`, error && `${id}-err`].filter(Boolean).join(" ") || undefined;
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-semibold text-ink">
        {label}{optional && <span className="ml-1 font-normal text-muted">(optional)</span>}
      </label>
      {hint && <p id={`${id}-hint`} className="text-sm text-muted">{hint}</p>}
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {error && <p id={`${id}-err`} className="flex items-start gap-1.5 text-sm font-medium text-risk-high"><AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />{error}</p>}
    </div>
  );
}
export const inputCls = "block w-full rounded-md border border-line-strong bg-surface px-3 py-2.5 text-base text-ink placeholder:text-muted/80 aria-[invalid=true]:border-risk-high";

export function Alert({ tone = "error", title, children, action }) {
  const tones = { error: "border-risk-high bg-risk-high-bg", warn: "border-risk-med bg-risk-med-bg", info: "border-line-strong bg-note-bg" };
  const Icon = tone === "info" ? Info : TriangleAlert;
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cx("flex gap-3 rounded-md border-l-4 p-4", tones[tone])}>
      <Icon className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1 space-y-1">
        {title && <p className="font-semibold">{title}</p>}
        <div className="text-sm">{children}</div>
        {action && <div className="pt-2">{action}</div>}
      </div>
    </div>
  );
}

export function ErrorState({ error, onRetry }) {
  return (
    <Alert title="Something went wrong" action={onRetry && <Button variant="secondary" onClick={onRetry}>Try again</Button>}>
      <p>{error?.message || "Unexpected error."}</p>
      {error?.requestId && <p className="text-muted">Reference: {error.requestId}</p>}
    </Alert>
  );
}

export function EmptyState({ title, children, action }) {
  return (
    <div className="rounded-md border border-dashed border-line-strong px-6 py-12 text-center">
      <h2 className="font-serif text-2xl">{title}</h2>
      <p className="mx-auto mt-2 max-w-md text-muted">{children}</p>
      {action && <div className="mt-6 flex justify-center">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }) { return <div className={cx("skeleton", className)} aria-hidden="true" />; }
export function LoadingBlock({ label = "Loading" }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3">
      <span className="sr-only">{label}…</span>
      <Skeleton className="h-8 w-1/3" /><Skeleton className="h-24 w-full" /><Skeleton className="h-24 w-full" />
    </div>
  );
}

const ICON = { low: CheckCircle2, medium: TriangleAlert, high: OctagonAlert };
const TONE = { low: "text-risk-low bg-risk-low-bg border-risk-low", medium: "text-risk-med bg-risk-med-bg border-risk-med", high: "text-risk-high bg-risk-high-bg border-risk-high" };
export function RiskBadge({ level, status, errorCode }) {
  if (status === "failed") return <span className="inline-flex items-center gap-1 rounded-full border border-line-strong bg-note-bg px-2.5 py-0.5 text-sm font-semibold text-ink-soft"><AlertTriangle className="size-4" aria-hidden="true" />{errorCode === "not_job_posting" ? "Not assessed" : "Failed"}</span>;
  if (!level) return null;
  const Icon = ICON[level];
  return <span className={cx("inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-sm font-semibold", TONE[level])}><Icon className="size-4" aria-hidden="true" />{RISK[level].label}</span>;
}

/** Score 0-100 on a track with labelled zones; text states the level so colour is never the only cue. */
export function ScoreGauge({ score, level }) {
  const Icon = ICON[level] || ShieldCheck;
  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <p className="font-serif text-6xl leading-none tabular-nums">{score}<span className="text-2xl text-muted"> / 100</span></p>
        <p className={cx("inline-flex items-center gap-1.5 text-lg font-semibold", TONE[level].split(" ")[0])}><Icon className="size-5" aria-hidden="true" />{RISK[level].label}: {RISK[level].note.toLowerCase()}</p>
      </div>
      <div className="relative mt-5" role="img" aria-label={`Risk score ${score} out of 100, ${RISK[level].label}. Zones: low 0 to 34, medium 35 to 59, high 60 to 100.`}>
        <div className="flex h-3 overflow-hidden rounded-full border border-line-strong">
          <div className="bg-risk-low-bg" style={{ width: "35%" }} /><div className="bg-risk-med-bg" style={{ width: "25%" }} /><div className="bg-risk-high-bg" style={{ width: "40%" }} />
        </div>
        <div className="gauge-marker absolute -top-1.5 h-6 w-1 -translate-x-1/2 rounded bg-ink" style={{ left: `${Math.min(100, Math.max(0, score))}%` }} />
        <div className="mt-1.5 flex text-xs text-muted" aria-hidden="true"><span style={{ width: "35%" }}>Low 0–34</span><span style={{ width: "25%" }}>Medium 35–59</span><span>High 60–100</span></div>
      </div>
    </div>
  );
}

export function Pagination({ page, totalPages, onChange }) {
  if (totalPages <= 1) return null;
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-3 pt-4">
      <Button variant="secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</Button>
      <p className="text-sm text-muted" aria-live="polite">Page {page} of {totalPages}</p>
      <Button variant="secondary" disabled={page >= totalPages} onClick={() => onChange(page + 1)}>Next</Button>
    </nav>
  );
}

// ---- toasts
const ToastCtx = createContext({ push: () => {} });
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const push = useCallback((message, tone = "info") => setItems((s) => [...s, { id: crypto.randomUUID(), message, tone }]), []);
  const remove = (id) => setItems((s) => s.filter((t) => t.id !== id));
  return (
    <ToastCtx.Provider value={{ push }}>
      {children}
      <div className="fixed inset-x-0 bottom-4 z-40 mx-auto flex max-w-md flex-col gap-2 px-4" role="status" aria-live="polite">
        {items.map((t) => <Toast key={t.id} {...t} onClose={() => remove(t.id)} />)}
      </div>
    </ToastCtx.Provider>
  );
}
function Toast({ message, tone, onClose }) {
  useEffect(() => { const h = setTimeout(onClose, 5000); return () => clearTimeout(h); }, [onClose]);
  return (
    <div className={cx("flex items-start gap-3 rounded-md border bg-surface p-3 text-sm shadow-md", tone === "error" ? "border-risk-high" : "border-line-strong")}>
      <p className="flex-1">{message}</p>
      <button onClick={onClose} aria-label="Dismiss notification" className="rounded p-1 hover:bg-note-bg"><X className="size-4" aria-hidden="true" /></button>
    </div>
  );
}
