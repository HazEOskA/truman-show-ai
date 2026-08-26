"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Header } from "@/components/Page";
import { apiGet, Json, pct, useSelection } from "@/lib/api";

function CausalView() {
  const params = useSearchParams();
  const { worldId, timelineId } = useSelection();
  const [eventId, setEventId] = useState(params.get("event") ?? "");
  const [data, setData] = useState<Json | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(id: string) {
    if (!worldId || !id) return;
    setError(null);
    try {
      setData(await apiGet<Json>(`/worlds/${worldId}/timelines/${timelineId}/events/${id}/causes`));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  useEffect(() => {
    if (eventId) load(eventId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [worldId, timelineId]);

  return (
    <>
      <Header title="Causal graph" right="why did this happen?" />
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="row">
          <input
            style={{ width: 220 }}
            placeholder="evt_000000123"
            value={eventId}
            onChange={(event) => setEventId(event.target.value)}
          />
          <button className="primary" onClick={() => load(eventId)}>Trace</button>
        </div>
        {error ? <div className="error" style={{ marginTop: 8 }}>{error}</div> : null}
      </div>

      {data?.event ? (
        <div className="grid cols-2">
          <div className="card">
            <h3>Chain of causes (root first)</h3>
            {(data.chain as Json[]).length ? (
              <ol style={{ paddingLeft: 18 }}>
                {(data.chain as Json[]).map((node) => (
                  <li key={node.event.event_id} style={{ marginBottom: 6 }}>
                    <span className="muted">{node.event.sim_time}</span>{" "}
                    <strong>{String(node.event.action).replace(/_/g, " ")}</strong>{" "}
                    <span className="muted">
                      ({node.event.topic}, importance {pct(node.event.importance, 0)})
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <div className="muted">This event has no recorded cause — it is a root event.</div>
            )}
          </div>
          <div className="card">
            <h3>Consequences</h3>
            {(data.consequences as Json[]).length ? (
              <ul style={{ paddingLeft: 18 }}>
                {(data.consequences as Json[]).map((node) => (
                  <li key={node.event.event_id} style={{ marginBottom: 6 }}>
                    <span className="muted">{node.event.sim_time}</span>{" "}
                    {String(node.event.action).replace(/_/g, " ")}{" "}
                    <span className="muted">({node.event.topic})</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="muted">Nothing has followed from this yet.</div>
            )}
          </div>
        </div>
      ) : (
        <div className="card muted">
          Paste an event id (from the Events view) to see the chain the world actually produced.
        </div>
      )}
    </>
  );
}

export default function CausalPage() {
  return (
    <Suspense fallback={<div className="empty">loading…</div>}>
      <CausalView />
    </Suspense>
  );
}
