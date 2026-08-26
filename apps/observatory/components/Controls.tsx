"use client";

import { useState } from "react";
import { apiPost, Json } from "@/lib/api";

export default function Controls({
  worldId,
  timelineId,
  control,
  onChanged
}: {
  worldId: string;
  timelineId: string;
  control: Json | null;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const base = `/worlds/${worldId}/timelines/${timelineId}`;

  async function send(body: Json) {
    setBusy(true);
    setError(null);
    try {
      await apiPost(`${base}/control`, body);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function scenario(name: string, params: Json = {}) {
    setBusy(true);
    setError(null);
    try {
      await apiPost(`${base}/scenario`, { name, params });
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const mode = control?.mode ?? "paused";
  const speed = control?.speed ?? 4;

  return (
    <div className="card">
      <h3>Run control</h3>
      <div className="row">
        <button
          className={mode === "running" ? "primary" : ""}
          disabled={busy || !worldId}
          onClick={() => send({ mode: mode === "running" ? "paused" : "running" })}
        >
          {mode === "running" ? "Pause" : "Run"}
        </button>
        <button disabled={busy || !worldId} onClick={() => send({ step_ticks: 6 })}>
          Step 1h
        </button>
        <button disabled={busy || !worldId} onClick={() => send({ step_ticks: 144 })}>
          Step 1 day
        </button>
        <span className="muted">speed</span>
        <select
          value={String(speed)}
          disabled={busy || !worldId}
          onChange={(event) => send({ speed: Number(event.target.value) })}
        >
          <option value="1">1 tick/s</option>
          <option value="4">4 ticks/s</option>
          <option value="12">12 ticks/s</option>
          <option value="48">48 ticks/s</option>
          <option value="0">as fast as possible</option>
        </select>
        <span className="pill">{mode}</span>
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <span className="muted">scenario</span>
        <button disabled={busy || !worldId} onClick={() => scenario("plant_failure", { loss: 0.4 })}>
          Plant −40%
        </button>
        <button disabled={busy || !worldId} onClick={() => scenario("cold_snap", { drop_c: 12 })}>
          Cold snap
        </button>
        <button disabled={busy || !worldId} onClick={() => scenario("supply_shock", { code: "materials", loss: 0.5 })}>
          Supply shock
        </button>
        <button disabled={busy || !worldId} onClick={() => scenario("plant_repair", {})}>
          Repair plant
        </button>
      </div>
      {control?.note ? <div className="muted" style={{ marginTop: 8 }}>{control.note}</div> : null}
      {error ? <div className="error" style={{ marginTop: 8 }}>{error}</div> : null}
    </div>
  );
}
