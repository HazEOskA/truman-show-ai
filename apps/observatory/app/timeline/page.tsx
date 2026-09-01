"use client";

import { useEffect, useState } from "react";
import { Header } from "@/components/Page";
import { useI18n } from "@/components/I18n";
import { apiGet, apiPost, Json, useSelection } from "@/lib/api";

export default function TimelinePage() {
  const { t } = useI18n();
  const { worldId, timelineId, select } = useSelection();
  const [timelines, setTimelines] = useState<Json[]>([]);
  const [snapshots, setSnapshots] = useState<number[]>([]);
  const [forkTick, setForkTick] = useState("");
  const [label, setLabel] = useState("");
  const [salt, setSalt] = useState("");
  const [replayTick, setReplayTick] = useState("");
  const [result, setResult] = useState<Json | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    if (!worldId) return;
    try {
      const data = await apiGet<{ timelines: Json[] }>(`/worlds/${worldId}/timelines`);
      setTimelines(data.timelines);
      const snaps = await apiGet<{ snapshots: number[] }>(
        `/worlds/${worldId}/timelines/${timelineId}/snapshots`
      );
      setSnapshots(snaps.snapshots);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [worldId, timelineId]);

  async function fork() {
    setBusy(true);
    setError(null);
    try {
      const created = await apiPost<Json>(`/worlds/${worldId}/timelines/${timelineId}/fork`, {
        fork_tick: Number(forkTick),
        label,
        divergence_salt: salt
      });
      setResult(created);
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function replay() {
    setBusy(true);
    setError(null);
    try {
      setResult(await apiGet<Json>(`/worlds/${worldId}/timelines/${timelineId}/replay?tick=${Number(replayTick)}`));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Header title={t("timeline.title")} right={t("timeline.summary", { count: timelines.length })} />
      <div className="grid cols-2" style={{ marginBottom: 12 }}>
        <div className="card">
          <h3>{t("timeline.timelines")}</h3>
          <table>
            <thead>
              <tr><th>{t("common.timeline")}</th><th>{t("timeline.parent")}</th><th className="num">{t("timeline.forkTick")}</th><th className="num">{t("timeline.head")}</th><th>{t("timeline.sealed")}</th><th /></tr>
            </thead>
            <tbody>
              {timelines.map((timeline) => (
                <tr key={timeline.timeline_id}>
                  <td>
                    {timeline.timeline_id}
                    {timeline.label ? <div className="muted">{timeline.label}</div> : null}
                  </td>
                  <td className="muted">{timeline.parent_timeline_id ?? "—"}</td>
                  <td className="num muted">{timeline.fork_tick ?? "—"}</td>
                  <td className="num">{timeline.head_tick}</td>
                  <td>{timeline.sealed ? <span className="pill on">{t("timeline.sealedValue")}</span> : <span className="pill">{t("common.open")}</span>}</td>
                  <td>
                    <button onClick={() => select(worldId, timeline.timeline_id)}>
                      {timeline.timeline_id === timelineId ? t("timeline.watching") : t("timeline.watch")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h3>{t("timeline.forkTitle")}</h3>
          <p className="muted">
            {t("timeline.forkCopy")}
          </p>
          <div className="row">
            <input placeholder={t("timeline.forkTickPlaceholder")} aria-label={t("timeline.forkTickPlaceholder")} value={forkTick} onChange={(e) => setForkTick(e.target.value)} style={{ width: 110 }} />
            <input placeholder={t("timeline.label")} aria-label={t("timeline.label")} value={label} onChange={(e) => setLabel(e.target.value)} />
            <input placeholder={t("timeline.salt")} aria-label={t("timeline.salt")} value={salt} onChange={(e) => setSalt(e.target.value)} style={{ width: 140 }} />
            <button className="primary" disabled={busy || !forkTick} onClick={fork}>{t("timeline.fork")}</button>
          </div>
          <h3 style={{ marginTop: 14 }}>{t("timeline.replay")}</h3>
          <div className="row">
            <input placeholder={t("common.tick")} aria-label={t("common.tick")} value={replayTick} onChange={(e) => setReplayTick(e.target.value)} style={{ width: 110 }} />
            <button disabled={busy || !replayTick} onClick={replay}>{t("timeline.replayVerify")}</button>
          </div>
          <div className="muted" style={{ marginTop: 8 }}>
            {t("timeline.snapshots", { values: snapshots.length ? snapshots.join(", ") : t("timeline.noSnapshots") })}
          </div>
          {error ? <div className="error" role="alert" style={{ marginTop: 8 }}>{t("common.error", { message: error })}</div> : null}
          {result ? (
            <pre style={{ marginTop: 10, whiteSpace: "pre-wrap", color: "var(--accent)" }}>
              {JSON.stringify(result, null, 2)}
            </pre>
          ) : null}
        </div>
      </div>
    </>
  );
}
