"use client";

import { useEffect, useState } from "react";
import { apiGet, apiPost, Json } from "@/lib/api";

export default function WorldPicker({
  worldId,
  timelineId,
  onSelect
}: {
  worldId: string;
  timelineId: string;
  onSelect: (world: string, timeline: string) => void;
}) {
  const [worlds, setWorlds] = useState<Json[]>([]);
  const [timelines, setTimelines] = useState<Json[]>([]);
  const [seed, setSeed] = useState("20260826");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadWorlds() {
    try {
      const data = await apiGet<{ worlds: Json[] }>("/worlds");
      setWorlds(data.worlds);
      if (!worldId && data.worlds.length) {
        onSelect(data.worlds[0].world_id, "tl_zero");
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }

  useEffect(() => {
    loadWorlds();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!worldId) return;
    apiGet<{ timelines: Json[] }>(`/worlds/${worldId}/timelines`)
      .then((data) => setTimelines(data.timelines))
      .catch(() => undefined);
  }, [worldId]);

  async function createWorld() {
    setBusy(true);
    setError(null);
    try {
      const created = await apiPost<Json>("/worlds", { seed: Number(seed) });
      await loadWorlds();
      onSelect(created.world_id, created.timeline_id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card world-picker">
      <h3>World selection</h3>
      <div className="row world-picker-row">
        <label className="sr-only" htmlFor="world-select">World</label>
        <select id="world-select" value={worldId} onChange={(event) => onSelect(event.target.value, "tl_zero")}>
          <option value="">— select —</option>
          {worlds.map((world) => (
            <option key={world.world_id} value={world.world_id}>
              {world.world_id} (seed {world.seed})
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="timeline-select">Timeline</label>
        <select id="timeline-select" value={timelineId} onChange={(event) => onSelect(worldId, event.target.value)}>
          {(timelines.length ? timelines : [{ timeline_id: "tl_zero", label: "Timeline Zero" }]).map((t) => (
            <option key={t.timeline_id} value={t.timeline_id}>
              {t.timeline_id} {t.label ? `— ${t.label}` : ""}
            </option>
          ))}
        </select>
      </div>
      <div className="row world-genesis">
        <label className="muted" htmlFor="world-seed">New world seed</label>
        <input id="world-seed" value={seed} onChange={(event) => setSeed(event.target.value)} />
        <button className="primary" disabled={busy} onClick={createWorld}>
          {busy ? "creating…" : "Genesis"}
        </button>
      </div>
      {error ? <div className="error world-picker-error">{error}</div> : null}
    </div>
  );
}
