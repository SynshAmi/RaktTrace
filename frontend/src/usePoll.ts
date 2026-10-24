import { useEffect, useRef, useState } from "react";

export const POLL_MS = 2000;

/**
 * Loads now, again every `everyMs`, and again whenever `key` or `version` changes (version bumps after a control).
 * Skips while `paused`, so no poll races a control that replaces the world (a reset would 404 the old request).
 */
export function usePoll<T>(load: () => Promise<T>, key: string, version: number, everyMs = POLL_MS, paused = false) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => {
    setData(null);
    setError(null);
  }, [key]);

  useEffect(() => {
    let alive = true;
    const run = () =>
      !pausedRef.current &&
      loadRef.current().then(
        (d) => alive && (setData(d), setError(null)),
        (e: Error) => alive && setError(e.message),
      );
    run();
    const timer = setInterval(run, everyMs);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [key, version, everyMs]);

  return { data, error };
}
