"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Header } from "@/components/Page";
import { useI18n } from "@/components/I18n";
import { apiGet, Json, pct, useSelection } from "@/lib/api";

function CausalView() {
  const { t, term } = useI18n();
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
      <Header title={t("causal.title")} right={t("causal.question")} />
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="row">
          <input
            style={{ width: 220 }}
            placeholder="evt_000000123"
            aria-label={t("causal.eventId")}
            value={eventId}
            onChange={(event) => setEventId(event.target.value)}
          />
          <button className="primary" onClick={() => load(eventId)}>{t("causal.trace")}</button>
        </div>
        {error ? <div className="error" role="alert" style={{ marginTop: 8 }}>{t("common.error", { message: error })}</div> : null}
      </div>

      {data?.event ? (
        <div className="grid cols-2">
          <div className="card">
            <h3>{t("causal.causes")}</h3>
            {(data.chain as Json[]).length ? (
              <ol style={{ paddingLeft: 18 }}>
                {(data.chain as Json[]).map((node) => (
                  <li key={node.event.event_id} style={{ marginBottom: 6 }}>
                    <span className="muted">{node.event.sim_time}</span>{" "}
                    <strong>{term(node.event.action)}</strong>{" "}
                    <span className="muted">
                      ({term(node.event.topic)}, {t("causal.importance", { value: pct(node.event.importance, 0) })})
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <div className="muted">{t("causal.root")}</div>
            )}
          </div>
          <div className="card">
            <h3>{t("causal.consequences")}</h3>
            {(data.consequences as Json[]).length ? (
              <ul style={{ paddingLeft: 18 }}>
                {(data.consequences as Json[]).map((node) => (
                  <li key={node.event.event_id} style={{ marginBottom: 6 }}>
                    <span className="muted">{node.event.sim_time}</span>{" "}
                    {term(node.event.action)}{" "}
                    <span className="muted">({term(node.event.topic)})</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="muted">{t("causal.noConsequences")}</div>
            )}
          </div>
        </div>
      ) : (
        <div className="card muted">
          {t("causal.prompt")}
        </div>
      )}
    </>
  );
}

export default function CausalPage() {
  const { t } = useI18n();
  return (
    <Suspense fallback={<div className="empty">{t("common.loading")}</div>}>
      <CausalView />
    </Suspense>
  );
}
