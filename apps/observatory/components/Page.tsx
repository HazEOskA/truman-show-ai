"use client";

import { Json, usePolling, useSelection } from "@/lib/api";

/** Every view is the same shape: pick a world, poll one projection, render it. */
export function useView<T = Json>(path: string, intervalMs = 3000) {
  const { worldId, timelineId } = useSelection();
  const base = worldId ? `/worlds/${worldId}/timelines/${timelineId}` : null;
  const { data, error, loading, refresh } = usePolling<T>(base ? `${base}${path}` : null, intervalMs);
  return { worldId, timelineId, base, data, error, loading, refresh };
}

export function Header({ title, right }: { title: string; right?: React.ReactNode }) {
  return (
    <div className="topbar">
      <h2>{title}</h2>
      {right ? <div className="clock">{right}</div> : null}
    </div>
  );
}

export function Guard({
  loading,
  error,
  data,
  children
}: {
  loading: boolean;
  error: string | null;
  data: unknown;
  children: React.ReactNode;
}) {
  if (error) return <div className="error">{error}</div>;
  if (loading) return <div className="empty">loading…</div>;
  if (!data) return <div className="empty">No world selected — open the World view first.</div>;
  return <>{children}</>;
}
