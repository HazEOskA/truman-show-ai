"use client";

import { useCallback, useEffect, useRef, useState } from "react";

declare global {
  interface Window {
    __HYDRA_API_URL__?: string;
  }
}

/**
 * Where the API lives, resolved when it is used rather than when the bundle is built.
 *
 * `NEXT_PUBLIC_*` values are inlined at build time, which means one image can only ever talk
 * to one API. That is fine locally and wrong everywhere else: on Cloud Run you do not know
 * the API's URL until after you have deployed it, so a build-time value forces you to build
 * the front end twice. The server injects the runtime value into `window.__HYDRA_API_URL__`
 * (see `app/layout.tsx`); the build-time value is the fallback, and localhost is the
 * fallback's fallback.
 */
export function apiUrl(): string {
  if (typeof window !== "undefined" && window.__HYDRA_API_URL__) {
    return window.__HYDRA_API_URL__;
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

/** @deprecated Prefer {@link apiUrl}; this is only correct after hydration. */
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Json = Record<string, any>;

export async function apiGet<T = Json>(path: string): Promise<T> {
  const response = await fetch(`${apiUrl()}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${path}`);
  }
  return (await response.json()) as T;
}

export async function apiPost<T = Json>(path: string, body: Json): Promise<T> {
  const response = await fetch(`${apiUrl()}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

/** Which world and timeline the operator is currently watching. */
export function useSelection() {
  const [worldId, setWorldId] = useState<string>("");
  const [timelineId, setTimelineId] = useState<string>("tl_zero");

  useEffect(() => {
    const storedWorld = window.localStorage.getItem("hydra.world");
    const storedTimeline = window.localStorage.getItem("hydra.timeline");
    if (storedWorld) setWorldId(storedWorld);
    if (storedTimeline) setTimelineId(storedTimeline);
    if (!storedWorld) {
      apiGet<{ worlds: Json[] }>("/worlds")
        .then((data) => {
          if (data.worlds.length) {
            setWorldId(data.worlds[0].world_id);
            window.localStorage.setItem("hydra.world", data.worlds[0].world_id);
          }
        })
        .catch(() => undefined);
    }
  }, []);

  const select = useCallback((world: string, timeline: string) => {
    setWorldId(world);
    setTimelineId(timeline);
    window.localStorage.setItem("hydra.world", world);
    window.localStorage.setItem("hydra.timeline", timeline);
  }, []);

  return { worldId, timelineId, select };
}

/** Poll an endpoint. The Observatory watches; it never drives the simulation. */
export function usePolling<T = Json>(path: string | null, intervalMs = 2000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    if (!path) return;
    try {
      const result = await apiGet<T>(path);
      setData(result);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    if (!path) {
      setLoading(false);
      return;
    }
    setLoading(true);
    refresh();
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(refresh, intervalMs);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [path, intervalMs, refresh]);

  return { data, error, loading, refresh };
}

export function fmt(value: number | undefined | null, digits = 2): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return value.toFixed(digits);
}

export function pct(value: number | undefined | null, digits = 1): string {
  if (value === undefined || value === null) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function money(value: number | undefined | null): string {
  if (value === undefined || value === null) return "—";
  return `${fmt(value)} HYD`;
}
