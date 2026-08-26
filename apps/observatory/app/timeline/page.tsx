"use client";

import { useEffect, useState } from "react";
import { Header } from "@/components/Page";
import { apiGet, apiPost, Json, useSelection } from "@/lib/api";

export default function TimelinePage() {
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
      <Header title="Timeline" right={`${timelines.length} timelines`} />
      <div className="grid cols-2" style={{ marginBottom: 12 }}>
        <div className="card">
          <h3>Timelines</h3>
          <table>
            <thead>
              <tr><th>Timeline</th><th>Parent</th><th className="num">Fork tick</th><th className="num">Head</th><th>Sealed</th><th /></tr>
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
                  <td>{timeline.sealed ? <span className="pill on">sealed</span> : <span className="pill">open</span>}</td>
                  <td>
                    <button onClick={() => select(worldId, timeline.timeline_id)}>
                      {timeline.timeline_id === timelineId ? "watching" : "watch"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h3>Fork this timeline</h3>
          <p className="muted">
            Timeline Zero is immutable. Experiments run on branches: a fork copies the world at a tick and
            carries its own seed lineage from there.
          </p>
          <div className="row">
            <input placeholder="fork tick" value={forkTick} onChange={(e) => setForkTick(e.target.value)} style={{ width: 110 }} />
            <input placeholder="label" value={label} onChange={(e) => setLabel(e.target.value)} />
            <input placeholder="divergence salt" value={salt} onChange={(e) => setSalt(e.target.value)} style={{ width: 140 }} />
            <button className="primary" disabled={busy || !forkTick} onClick={fork}>Fork</button>
          </div>
          <h3 style={{ marginTop: 14 }}>Replay</h3>
          <div className="row">
            <input placeholder="tick" value={replayTick} onChange={(e) => setReplayTick(e.target.value)} style={{ width: 110 }} />
            <button disabled={busy || !replayTick} onClick={replay}>Replay &amp; verify</button>
          </div>
          <div className="muted" style={{ marginTop: 8 }}>
            snapshots at: {snapshots.length ? snapshots.join(", ") : "none yet"}
          </div>
          {error ? <div className="error" style={{ marginTop: 8 }}>{error}</div> : null}
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
