import { useEffect, useRef, useState } from "react";

import { api } from "./api";
import type { Health } from "./types";

interface Loaded<T> {
  key: string;
  data: T | null;
  error: string | null;
}

/** Load something whenever ``deps`` change (or on ``reload``), with loading and error state.
 * Results are kept per ``deps``, so switching to other deps shows "loading" instead of old data,
 * while a reload keeps showing the current data until the new answer arrives. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const key = JSON.stringify(deps);
  const [version, setVersion] = useState(0);
  const [loaded, setLoaded] = useState<Loaded<T> | null>(null);
  const latest = useRef(load);
  useEffect(() => {
    latest.current = load;
  });

  useEffect(() => {
    let alive = true;
    latest
      .current()
      .then((data) => alive && setLoaded({ key, data, error: null }))
      .catch(
        (err: unknown) => alive && setLoaded({ key, data: null, error: err instanceof Error ? err.message : String(err) }),
      );
    return () => {
      alive = false;
    };
  }, [key, version]);

  const current = loaded?.key === key ? loaded : null;
  return { data: current?.data ?? null, error: current?.error ?? null, reload: () => setVersion((v) => v + 1) };
}

/** Call ``tick`` every ``ms`` until it returns true (done) or the component unmounts. */
export function usePoll(tick: () => Promise<boolean>, ms: number, enabled: boolean) {
  const tickRef = useRef(tick);
  useEffect(() => {
    tickRef.current = tick;
  });
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let timer: number | undefined;
    const run = async () => {
      const done = await tickRef.current().catch(() => false);
      if (alive && !done) timer = window.setTimeout(run, ms);
    };
    void run();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [ms, enabled]);
}

export function useHealth() {
  return useLoad<Health>(() => api.health(), []);
}

type Theme = "light" | "dark";

export function useTheme(): [Theme, () => void] {
  const initial = (): Theme => {
    const set = document.documentElement.dataset.theme;
    if (set === "dark" || set === "light") return set;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  };
  const [theme, setTheme] = useState<Theme>(initial);
  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("shipshape-theme", next);
    } catch {
      // the theme still applies for this visit
    }
    setTheme(next);
  };
  return [theme, toggle];
}
