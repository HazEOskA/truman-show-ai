"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18n";
import { apiGet, apiPost, Json } from "@/lib/api";

export default function WorldPicker({
  worldId,
  timelineId,
  onSelect,
  variant = "legacy"
}: {
  worldId: string;
  timelineId: string;
  onSelect: (world: string, timeline: string) => void;
  variant?: "legacy" | "command";
}) {
  const { t } = useI18n();
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

  if (variant === "legacy") {
    return (
      <div className="card">
        <h3>{t("picker.world")}</h3>
        <div className="row">
          <select value={worldId} onChange={(event) => onSelect(event.target.value, "tl_zero")}>
            <option value="">{t("common.select")}</option>
            {worlds.map((world) => (
              <option key={world.world_id} value={world.world_id}>
                {world.world_id} ({t("picker.seed")} {world.seed})
              </option>
            ))}
          </select>
          <select value={timelineId} onChange={(event) => onSelect(worldId, event.target.value)}>
            {(timelines.length ? timelines : [{ timeline_id: "tl_zero", label: t("picker.timelineZero") }]).map((timeline) => (
              <option key={timeline.timeline_id} value={timeline.timeline_id}>
                {timeline.timeline_id} {timeline.label ? `— ${timeline.label}` : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <span className="muted">{t("picker.newSeed")}</span>
          <input value={seed} onChange={(event) => setSeed(event.target.value)} style={{ width: 120 }} />
          <button className="primary" disabled={busy} onClick={createWorld}>
            {busy ? t("picker.creating") : t("picker.genesis")}
          </button>
        </div>
        {error ? <div className="error" role="alert" style={{ marginTop: 8 }}>{t("common.error", { message: error })}</div> : null}
      </div>
    );
  }

  return (
    <div className="card control-card world-picker-card">
      <div className="control-card-header">
        <span className="control-index">01</span>
        <div>
          <h3>{t("picker.worldCoordinates")}</h3>
          <p>{t("picker.copy")}</p>
        </div>
        <span className="control-state">{t("common.source")}</span>
      </div>
      <div className="control-fields">
        <label>
          <span>{t("picker.worldInstance")}</span>
          <select value={worldId} onChange={(event) => onSelect(event.target.value, "tl_zero")}>
            <option value="">{t("common.select")}</option>
            {worlds.map((world) => (
              <option key={world.world_id} value={world.world_id}>
                {world.world_id} ({t("picker.seed")} {world.seed})
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>{t("picker.timeline")}</span>
          <select value={timelineId} onChange={(event) => onSelect(worldId, event.target.value)}>
            {(timelines.length ? timelines : [{ timeline_id: "tl_zero", label: t("picker.timelineZero") }]).map((timeline) => (
              <option key={timeline.timeline_id} value={timeline.timeline_id}>
                {timeline.timeline_id} {timeline.label ? `— ${timeline.label}` : ""}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="genesis-row">
        <label>
          <span>{t("picker.newSeed")}</span>
          <input value={seed} onChange={(event) => setSeed(event.target.value)} inputMode="numeric" />
        </label>
        <button className="primary" disabled={busy} onClick={createWorld}>
          {busy ? t("picker.creating") : t("picker.genesis")}
        </button>
      </div>
      {error ? <div className="error" role="alert" style={{ marginTop: 8 }}>{t("common.error", { message: error })}</div> : null}
    </div>
  );
}
