import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./api";

/** The page being shown, taken from the part of the address after "#". */
export function useRoute(): string[] {
  const read = () => window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const [route, setRoute] = useState<string[]>(read);
  useEffect(() => {
    const onChange = () => {
      setRoute(read());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export type Loaded<T> = { data: T | null; error: string | null; loading: boolean; reload: () => void };

/** Asks the server for something and tracks whether it is loading, loaded or failed. */
export function useLoad<T>(ask: () => Promise<T>, key: string, onLoggedOut: () => void): Loaded<T> {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({
    data: null, error: null, loading: true,
  });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState((previous) => ({ ...previous, loading: true, error: null }));
    ask()
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((problem) => {
        if (cancelled) return;
        if (problem instanceof ApiError && problem.status === 401) return onLoggedOut();
        const message = problem instanceof ApiError ? problem.message : "Could not reach the server.";
        setState({ data: null, error: message, loading: false });
      });
    return () => {
      cancelled = true;
    };
    // `ask` is rebuilt on every render; `key` says when the question really changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, reload };
}
