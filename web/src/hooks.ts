import { useCallback, useEffect, useState } from "react";
import { ApiError , WATCHLIST_CHANGED } from "./api";

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
  // Some things are shown in several places at once (the watchlist). When one place changes
  // it, the others are told and read it again.
  useEffect(() => {
    if (key !== "watchlist") return;
    window.addEventListener(WATCHLIST_CHANGED, reload);
    return () => window.removeEventListener(WATCHLIST_CHANGED, reload);
  }, [key, reload]);
  return { ...state, reload };
}

/** True while the screen is narrower than the given width, so a page can move a panel nearer the top. */
export function useNarrow(width = 1150): boolean {
  const query = `(max-width: ${width}px)`;
  const read = () => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(query).matches;
  const [narrow, setNarrow] = useState<boolean>(read);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(query);
    const change = () => setNarrow(list.matches);
    change();
    list.addEventListener("change", change);
    return () => list.removeEventListener("change", change);
  }, [query]);
  return narrow;
}
