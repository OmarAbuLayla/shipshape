import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "./api";
import type { Health } from "./types";

/** Load something once, with loading and error state. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stableLoad = useCallback(load, deps);

  useEffect(() => {
    let alive = true;
    setError(null);
    stableLoad()
      .then((value) => alive && setData(value))
      .catch((err: unknown) => alive && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      alive = false;
    };
  }, [stableLoad, version]);

  return { data, error, reload: () => setVersion((v) => v + 1) };
}

/** Call ``tick`` every ``ms`` until it returns true (done) or the component unmounts. */
export function usePoll(tick: () => Promise<boolean>, ms: number, enabled: boolean) {
  const tickRef = useRef(tick);
  tickRef.current = tick;
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let timer: number | undefined;
    const run = async () => {
      let done = false;
      try {
        done = await tickRef.current();
      } catch {
        done = false;
      }
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
