"use client";

import Link from "next/link";
import { useState } from "react";
import { Guard, Header, useView } from "@/components/Page";
import { fmt, Json, pct } from "@/lib/api";

const TOPICS = [
  ["", "All"],
  ["company.*", "Companies"],
  ["market.*", "Markets"],
  ["env.*", "Environment"],
  ["gov.*", "Government"],
  ["person.*", "People"],
  ["media.publish", "Media"],
  ["tech.*", "Technology"]
];

export default function EventsPage() {
  const [topic, setTopic] = useState("");
  const [minImportance, setMinImportance] = useState(0.2);
  const { data, error, loading } = useView<Json>(
    `/events?limit=200&topic=${encodeURIComponent(topic)}&min_importance=${minImportance}`,
    2500
  );

  return (
    <>
      <Header title="Events" right="immutable ledger" />
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="row">
          {TOPICS.map(([value, label]) => (
            <button key={value} className={topic === value ? "primary" : ""} onClick={() => setTopic(value)}>
              {label}
            </button>
          ))}
          <span className="muted">min importance</span>
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
                <tr><th className="num">Tick</th><th>Time</th><th>Topic</th><th>Action</th><th>Actor</th>
                  <th>Target</th><th className="num">Importance</th><th>Why</th></tr>
              </thead>
              <tbody>
                {((data?.events ?? []) as Json[]).map((event) => (
                  <tr key={event.event_id}>
                    <td className="num muted">{event.tick}</td>
                    <td className="muted">{event.sim_time}</td>
                    <td className="muted">{event.topic}</td>
                    <td>{String(event.action).replace(/_/g, " ")}</td>
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
                      <Link href={`/causal?event=${event.event_id}`}>chain</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!((data?.events ?? []) as Json[]).length ? (
            <div className="muted">
              No events yet at this importance. Ledgered events start once the world runs.
            </div>
          ) : null}
        </div>
      </Guard>
    </>
  );
}
