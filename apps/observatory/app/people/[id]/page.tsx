"use client";

import { use } from "react";
import Link from "next/link";
import { Guard, Header } from "@/components/Page";
import { Bar } from "@/components/Widgets";
import { fmt, Json, money, pct, usePolling, useSelection } from "@/lib/api";

export default function PersonPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { worldId, timelineId } = useSelection();
  const path = worldId ? `/worlds/${worldId}/timelines/${timelineId}/people/${id}` : null;
  const { data, error, loading } = usePolling<Json>(path, 2000);

  return (
    <>
      <Header
        title={data ? String(data.name) : "Person"}
        right={data ? `${data.tier === "A" ? "persistent agent" : "lightweight agent"} · ${data.activity}` : ""}
      />
      <p style={{ marginTop: -8, marginBottom: 12 }}>
        <Link href="/people">← all people</Link>
      </p>
      <Guard loading={loading} error={error} data={data}>
        {data ? (
          <div className="grid cols-3">
            <div className="card">
              <h3>Identity</h3>
              <table>
                <tbody>
                  <tr><td>age</td><td className="num">{fmt(data.age, 1)}</td></tr>
                  <tr><td>district</td><td className="num">{String(data.district).replace("district_", "")}</td></tr>
                  <tr><td>occupation</td><td className="num">{data.occupation}</td></tr>
                  <tr><td>employer</td><td className="num">{data.employer?.name ?? "—"}</td></tr>
                  <tr><td>status</td><td className="num">{data.employment}</td></tr>
                  <tr><td>wage</td><td className="num">{money(data.wage)}</td></tr>
                  <tr><td>wealth</td><td className="num">{money(data.wealth)}</td></tr>
                </tbody>
              </table>
            </div>

            <div className="card">
              <h3>Condition</h3>
              <table>
                <tbody>
                  <tr><td>health</td><td><Bar value={data.health} /></td><td className="num">{pct(data.health, 0)}</td></tr>
                  <tr><td>energy</td><td><Bar value={data.energy} /></td><td className="num">{pct(data.energy, 0)}</td></tr>
                  <tr><td>stress</td><td><Bar value={data.stress} tone="var(--bad)" /></td><td className="num">{pct(data.stress, 0)}</td></tr>
                  <tr><td>mood</td><td><Bar value={data.mood} tone="var(--good)" /></td><td className="num">{pct(data.mood, 0)}</td></tr>
                  <tr><td>political trust</td><td><Bar value={data.political_trust} tone="var(--accent-2)" /></td><td className="num">{pct(data.political_trust, 0)}</td></tr>
                </tbody>
              </table>
              <h3 style={{ marginTop: 12 }}>Needs</h3>
              <table>
                <tbody>
                  {Object.entries(data.needs as Json).map(([key, value]) => (
                    <tr key={key}>
                      <td>{key}</td>
                      <td><Bar value={Number(value)} /></td>
                      <td className="num">{pct(Number(value), 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="card">
              <h3>What they carry</h3>
              <table>
                <tbody>
                  <tr><td>known facts</td><td className="num">{data.counts.known_facts}</td></tr>
                  <tr><td>beliefs</td><td className="num">{data.counts.beliefs}</td></tr>
                  <tr><td>relationships</td><td className="num">{data.counts.relationships}</td></tr>
                  <tr><td>memories</td><td className="num">{data.counts.memories}</td></tr>
                  <tr><td>LLM calls today</td><td className="num">{data.compute_budget.calls_used_today}/{data.compute_budget.llm_calls_per_day}</td></tr>
                  <tr><td>tokens today</td><td className="num">{fmt(data.compute_budget.tokens_used_today, 0)}</td></tr>
                </tbody>
              </table>
              <h3 style={{ marginTop: 12 }}>Goals</h3>
              {(data.goals as Json[]).length ? (
                <ul style={{ margin: 0, paddingLeft: 16 }}>
                  {(data.goals as Json[]).map((goal, index) => (
                    <li key={index}>{goal.label}</li>
                  ))}
                </ul>
              ) : (
                <div className="muted">no explicit goals</div>
              )}
            </div>

            <div className="card">
              <h3>Recent actions</h3>
              {(data.recent_actions as string[]).length ? (
                <ol style={{ margin: 0, paddingLeft: 18 }}>
                  {(data.recent_actions as string[]).map((action, index) => (
                    <li key={index}>{action}</li>
                  ))}
                </ol>
              ) : (
                <div className="muted">nothing yet</div>
              )}
            </div>

            <div className="card">
              <h3>Known facts (subjective)</h3>
              <div className="scroll">
                <table>
                  <thead>
                    <tr><th>Topic</th><th>What they believe</th><th className="num">Conf.</th><th>Source</th></tr>
                  </thead>
                  <tbody>
                    {(data.known_facts as Json[]).map((fact) => (
                      <tr key={fact.fact_id}>
                        <td className="muted">{fact.topic}</td>
                        <td className={fact.distorted ? "warn" : ""}>{fact.text || fmt(fact.value)}</td>
                        <td className="num">{pct(fact.confidence, 0)}</td>
                        <td className="muted">{fact.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card">
              <h3>Memory &amp; relationships</h3>
              <div className="scroll">
                <table>
                  <thead><tr><th className="num">Tick</th><th>Memory</th><th className="num">Salience</th></tr></thead>
                  <tbody>
                    {(data.memories as Json[]).map((memory, index) => (
                      <tr key={index}>
                        <td className="num muted">{memory.tick}</td>
                        <td>{memory.summary}</td>
                        <td className="num">{pct(memory.salience, 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <table style={{ marginTop: 10 }}>
                  <thead><tr><th>Relation</th><th>With</th><th className="num">Trust</th><th className="num">Sentiment</th></tr></thead>
                  <tbody>
                    {(data.relationships as Json[]).map((edge, index) => (
                      <tr key={index}>
                        <td className="muted">{edge.relation}</td>
                        <td>
                          {String(edge.target).startsWith("person_") ? (
                            <Link href={`/people/${edge.target}`}>{edge.name}</Link>
                          ) : (
                            edge.name
                          )}
                        </td>
                        <td className="num">{pct(edge.trust, 0)}</td>
                        <td className="num">{fmt(edge.sentiment, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        ) : null}
      </Guard>
    </>
  );
}
