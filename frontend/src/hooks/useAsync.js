import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Minimal data-fetching hook. Runs fn(signal) whenever deps (or reload()) change and cancels stale requests.
 * `loading` is derived (result key !== current key), so no state is set synchronously inside an effect.
 */
export function useAsync(fn, deps) {
  const [tick, setTick] = useState(0);
  const [result, setResult] = useState({ key: null, data: null, error: null });
  const key = JSON.stringify([...deps, tick]);
  const fnRef = useRef(fn);
  useEffect(() => { fnRef.current = fn; });
  useEffect(() => {
    const ctl = new AbortController();
    fnRef.current(ctl.signal).then(
      (data) => { if (!ctl.signal.aborted) setResult({ key, data, error: null }); },
      (error) => { if (!ctl.signal.aborted && error.name !== "AbortError") setResult({ key, data: null, error }); },
    );
    return () => ctl.abort();
  }, [key]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  const loading = result.key !== key;
  return { data: loading ? null : result.data, error: loading ? null : result.error, loading, reload };
}
