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
    <div className="card control-card simulation-control-card">
      <div className="control-card-header">
        <span className="control-index">02</span>
        <div>
          <h3>Simulation control</h3>
          <p>Move time or inject a deterministic pressure.</p>
        </div>
        <span className={mode === "running" ? "control-state is-live" : "control-state"}>{mode}</span>
      </div>
      <div className="simulation-row">
        <span className="control-row-label">CLOCK</span>
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
        <label className="speed-field">
          <span>Speed</span>
          <select
            value={String(speed)}
            disabled={busy || !worldId}
            onChange={(event) => send({ speed: Number(event.target.value) })}
          >
            <option value="1">1 tick/s</option>
            <option value="4">4 ticks/s</option>
            <option value="12">12 ticks/s</option>
            <option value="48">48 ticks/s</option>
            <option value="0">maximum</option>
          </select>
        </label>
      </div>
      <div className="simulation-row simulation-row--scenario">
        <span className="control-row-label">PRESSURE</span>
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
