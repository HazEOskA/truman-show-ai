"use client";

import Link from "next/link";
import { useState } from "react";
import { Guard, Header, useView } from "@/components/Page";
import { useI18n } from "@/components/I18n";
import { fmt, Json, pct } from "@/lib/api";

const TOPICS = [
  ["", "events.all"],
  ["company.*", "events.companies"],
  ["market.*", "events.markets"],
  ["env.*", "events.environment"],
  ["gov.*", "events.government"],
  ["person.*", "events.people"],
  ["media.publish", "events.media"],
  ["tech.*", "events.technology"]
];

export default function EventsPage() {
  const { t, term } = useI18n();
  const [topic, setTopic] = useState("");
  const [minImportance, setMinImportance] = useState(0.2);
  const { data, error, loading } = useView<Json>(
    `/events?limit=200&topic=${encodeURIComponent(topic)}&min_importance=${minImportance}`,
    2500
  );

  return (
    <>
      <Header title={t("events.title")} right={t("events.immutable")} />
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="row">
          {TOPICS.map(([value, labelKey]) => (
            <button key={value} className={topic === value ? "primary" : ""} onClick={() => setTopic(value)}>
              {t(labelKey)}
            </button>
          ))}
          <span className="muted">{t("events.minImportance")}</span>
          <input
            type="range"
            min="0"
            max="0.9"
            step="0.05"
            value={minImportance}
            onChange={(event) => setMinImportance(Number(event.target.value))}
          />
          <span>{minImportance.toFixed(2)}</span>
        </div>
      </div>
      <Guard loading={loading} error={error} data={data}>
        <div className="card">
          <div className="scroll" style={{ maxHeight: 640 }}>
            <table>
              <thead>
                <tr><th className="num">{t("common.tick")}</th><th>{t("common.time")}</th><th>{t("common.topic")}</th><th>{t("common.action")}</th><th>{t("events.actor")}</th>
                  <th>{t("common.target")}</th><th className="num">{t("events.importance")}</th><th>{t("events.why")}</th></tr>
              </thead>
              <tbody>
                {((data?.events ?? []) as Json[]).map((event) => (
                  <tr key={event.event_id}>
                    <td className="num muted">{event.tick}</td>
                    <td className="muted">{event.sim_time}</td>
                    <td className="muted">{term(event.topic)}</td>
                    <td>{term(event.action)}</td>
                    <td className="muted">
                      {String(event.actor ?? "").startsWith("person_") ? (
                        <Link href={`/people/${event.actor}`}>{event.actor}</Link>
                      ) : (
                        event.actor ?? "—"
                      )}
                    </td>
                    <td className="muted">{event.target ?? "—"}</td>
                    <td className="num">{pct(event.importance, 0)}</td>
                    <td>
                      <Link href={`/causal?event=${event.event_id}`}>{t("events.chain")}</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!((data?.events ?? []) as Json[]).length ? (
            <div className="muted">
              {t("events.empty")}
            </div>
          ) : null}
        </div>
      </Guard>
    </>
  );
}
