import { useCallback, useEffect, useRef, useState } from 'react';
import { errorText, onChanged, type Source, type Sourced } from '../api/client';

export interface Resource<T> {
  data: T | undefined;
  source: Source | undefined;
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
}

/**
 * Load something from the API, refetch on an interval and whenever any action changes state.
 * Only re-renders when the answer actually changed, so polling doesn't flicker.
 */
export function useResource<T>(load: () => Promise<Sourced<T>>, deps: unknown[], opts: { intervalMs?: number } = {}): Resource<T> {
  const [state, setState] = useState<{ data?: T; source?: Source; error: string | null; loading: boolean }>({ error: null, loading: true });
  const loadRef = useRef(load);
  loadRef.current = load;
  const gen = useRef(0);
  const last = useRef('');

  const run = useCallback(async () => {
    const mine = gen.current;
    try {
      const r = await loadRef.current();
      if (mine !== gen.current) return;
      const json = JSON.stringify(r);
      if (json !== last.current) {
        last.current = json;
        setState({ data: r.data, source: r.source, error: null, loading: false });
      } else {
        setState((s) => (s.loading || s.error ? { ...s, loading: false, error: null } : s));
      }
    } catch (e) {
      if (mine !== gen.current) return;
      setState((s) => ({ ...s, loading: false, error: errorText(e) }));
    }
  }, []);

  useEffect(() => {
    gen.current += 1;
    last.current = '';
    setState({ error: null, loading: true });
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    if (!opts.intervalMs) return;
    const t = window.setInterval(() => void run(), opts.intervalMs);
    return () => window.clearInterval(t);
  }, [opts.intervalMs, run]);

  useEffect(() => onChanged(() => void run()), [run]);

  return { data: state.data, source: state.source, error: state.error, loading: state.loading, reload: run };
}
