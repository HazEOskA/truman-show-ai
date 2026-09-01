"use client";

import { use } from "react";
import Link from "next/link";
import { Guard, Header } from "@/components/Page";
import { useI18n } from "@/components/I18n";
import { Bar } from "@/components/Widgets";
import { fmt, Json, money, pct, usePolling, useSelection } from "@/lib/api";

export default function PersonPage({ params }: { params: Promise<{ id: string }> }) {
  const { t, term } = useI18n();
  const { id } = use(params);
  const { worldId, timelineId } = useSelection();
  const path = worldId ? `/worlds/${worldId}/timelines/${timelineId}/people/${id}` : null;
  const { data, error, loading } = usePolling<Json>(path, 2000);

  return (
    <>
      <Header
        title={data ? String(data.name) : t("person.title")}
        right={data ? `${data.tier === "A" ? t("person.persistent") : t("person.lightweight")} · ${term(data.activity)}` : ""}
      />
      <p style={{ marginTop: -8, marginBottom: 12 }}>
        <Link href="/people">{t("person.all")}</Link>
      </p>
      <Guard loading={loading} error={error} data={data}>
        {data ? (
          <div className="grid cols-3">
            <div className="card">
              <h3>{t("person.identity")}</h3>
              <table>
                <tbody>
                  <tr><td>{t("person.age")}</td><td className="num">{fmt(data.age, 1)}</td></tr>
                  <tr><td>{t("person.district")}</td><td className="num">{String(data.district).replace("district_", "")}</td></tr>
                  <tr><td>{t("person.occupation")}</td><td className="num">{term(data.occupation)}</td></tr>
                  <tr><td>{t("person.employer")}</td><td className="num">{data.employer?.name ?? "—"}</td></tr>
                  <tr><td>{t("person.status")}</td><td className="num">{term(data.employment)}</td></tr>
                  <tr><td>{t("person.wage")}</td><td className="num">{money(data.wage)}</td></tr>
                  <tr><td>{t("person.wealth")}</td><td className="num">{money(data.wealth)}</td></tr>
                </tbody>
              </table>
            </div>

            <div className="card">
              <h3>{t("person.condition")}</h3>
              <table>
                <tbody>
                  <tr><td>{t("person.health")}</td><td><Bar value={data.health} /></td><td className="num">{pct(data.health, 0)}</td></tr>
                  <tr><td>{t("person.energy")}</td><td><Bar value={data.energy} /></td><td className="num">{pct(data.energy, 0)}</td></tr>
                  <tr><td>{t("person.stress")}</td><td><Bar value={data.stress} tone="var(--bad)" /></td><td className="num">{pct(data.stress, 0)}</td></tr>
                  <tr><td>{t("person.mood")}</td><td><Bar value={data.mood} tone="var(--good)" /></td><td className="num">{pct(data.mood, 0)}</td></tr>
                  <tr><td>{t("person.politicalTrust")}</td><td><Bar value={data.political_trust} tone="var(--accent-2)" /></td><td className="num">{pct(data.political_trust, 0)}</td></tr>
                </tbody>
              </table>
              <h3 style={{ marginTop: 12 }}>{t("person.needs")}</h3>
              <table>
                <tbody>
                  {Object.entries(data.needs as Json).map(([key, value]) => (
                    <tr key={key}>
                      <td>{term(key)}</td>
                      <td><Bar value={Number(value)} /></td>
                      <td className="num">{pct(Number(value), 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="card">
              <h3>{t("person.carry")}</h3>
              <table>
                <tbody>
                  <tr><td>{t("person.knownFacts")}</td><td className="num">{data.counts.known_facts}</td></tr>
                  <tr><td>{t("person.beliefs")}</td><td className="num">{data.counts.beliefs}</td></tr>
                  <tr><td>{t("person.relationships")}</td><td className="num">{data.counts.relationships}</td></tr>
                  <tr><td>{t("person.memories")}</td><td className="num">{data.counts.memories}</td></tr>
                  <tr><td>{t("person.callsToday")}</td><td className="num">{data.compute_budget.calls_used_today}/{data.compute_budget.llm_calls_per_day}</td></tr>
                  <tr><td>{t("person.tokensToday")}</td><td className="num">{fmt(data.compute_budget.tokens_used_today, 0)}</td></tr>
                </tbody>
              </table>
              <h3 style={{ marginTop: 12 }}>{t("person.goals")}</h3>
              {(data.goals as Json[]).length ? (
                <ul style={{ margin: 0, paddingLeft: 16 }}>
                  {(data.goals as Json[]).map((goal, index) => (
                    <li key={index}>{goal.label}</li>
                  ))}
                </ul>
              ) : (
                <div className="muted">{t("person.noGoals")}</div>
              )}
            </div>

            <div className="card">
              <h3>{t("person.recentActions")}</h3>
              {(data.recent_actions as string[]).length ? (
                <ol style={{ margin: 0, paddingLeft: 18 }}>
                  {(data.recent_actions as string[]).map((action, index) => (
                    <li key={index}>{action}</li>
                  ))}
                </ol>
              ) : (
                <div className="muted">{t("person.nothingYet")}</div>
              )}
            </div>

            <div className="card">
              <h3>{t("person.subjectiveFacts")}</h3>
              <div className="scroll">
                <table>
                  <thead>
                    <tr><th>{t("person.factTopic")}</th><th>{t("person.belief")}</th><th className="num">{t("person.confidence")}</th><th>{t("person.source")}</th></tr>
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
              <h3>{t("person.memoryRelationships")}</h3>
              <div className="scroll">
                <table>
                  <thead><tr><th className="num">{t("common.tick")}</th><th>{t("person.memory")}</th><th className="num">{t("person.salience")}</th></tr></thead>
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
                  <thead><tr><th>{t("person.relation")}</th><th>{t("person.with")}</th><th className="num">{t("people.trust")}</th><th className="num">{t("person.sentiment")}</th></tr></thead>
                  <tbody>
                    {(data.relationships as Json[]).map((edge, index) => (
                      <tr key={index}>
                        <td className="muted">{term(edge.relation)}</td>
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
