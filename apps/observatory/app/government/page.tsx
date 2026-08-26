"use client";

import { Guard, Header, useView } from "@/components/Page";
import { Bar, Spark, Stat } from "@/components/Widgets";
import { fmt, Json, money, pct } from "@/lib/api";

export default function GovernmentPage() {
  const { data, error, loading } = useView<Json>("/government", 2500);
  return (
    <>
      <Header title="Government" right={data?.mayor ? `Mayor ${data.mayor.name}` : ""} />
      <Guard loading={loading} error={error} data={data}>
        {data ? (
          <>
            <div className="grid cols-6" style={{ marginBottom: 12 }}>
              <Stat label="Approval" value={pct(data.approval)} tone={data.approval < 0.35 ? "bad" : "good"} />
              <Stat label="Unrest" value={pct(data.unrest_index)} tone={data.unrest_index > 0.3 ? "bad" : undefined} />
              <Stat label="Emergency level" value={data.emergency_level} tone={data.emergency_level ? "warn" : undefined} />
              <Stat label="Treasury" value={money(data.treasury)} />
              <Stat label="Debt" value={money(data.debt)} />
              <Stat label="Public jobs" value={fmt(data.public_jobs, 0)} />
            </div>

            <div className="grid cols-2">
              <div className="card">
                <h3>Approval over time</h3>
                <Spark points={(data.approval_history ?? []) as number[]} width={460} height={70} colour="var(--good)" />
                <h3 style={{ marginTop: 14 }}>Parties</h3>
                <table>
                  <thead><tr><th>Party</th><th>Leader</th><th className="num">Support</th><th className="num">Seats</th></tr></thead>
                  <tbody>
                    {(data.parties as Json[]).map((party) => (
                      <tr key={party.id}>
                        <td>{party.name} {party.in_power ? <span className="pill on">in power</span> : null}</td>
                        <td className="muted">{party.leader || "—"}</td>
                        <td className="num"><Bar value={party.support} /></td>
                        <td className="num">{party.seats}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="card">
                <h3>Policies</h3>
                <div className="scroll">
                  <table>
                    <thead>
                      <tr><th>Policy</th><th>Target</th><th className="num">Value</th><th className="num">Cost/day</th><th className="num">Enacted</th><th>State</th></tr>
                    </thead>
                    <tbody>
                      {(data.policies as Json[]).map((policy) => (
                        <tr key={policy.id}>
                          <td>{policy.kind}</td>
                          <td className="muted">{policy.target || "—"}</td>
                          <td className="num">{fmt(policy.value, 3)}</td>
                          <td className="num">{money(policy.cost_per_day)}</td>
                          <td className="num muted">t{policy.enacted_tick}</td>
                          <td>{policy.active ? <span className="pill on">active</span> : <span className="pill">expired</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="card">
                <h3>Institutions</h3>
                <table>
                  <thead><tr><th>Institution</th><th>Leader</th><th className="num">Staff</th><th className="num">Budget</th><th className="num">Effectiveness</th></tr></thead>
                  <tbody>
                    {(data.institutions as Json[]).map((institution) => (
                      <tr key={institution.id}>
                        <td>{institution.name}</td>
                        <td className="muted">{institution.leader || "—"}</td>
                        <td className="num">{fmt(institution.staff, 0)}</td>
                        <td className="num">{money(institution.budget)}</td>
                        <td className="num"><Bar value={institution.effectiveness} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="card">
                <h3>Decision log</h3>
                {(data.decision_log as string[]).length ? (
                  <ol style={{ margin: 0, paddingLeft: 18 }}>
                    {(data.decision_log as string[]).slice().reverse().map((line, index) => (
                      <li key={index} className="muted">{line}</li>
                    ))}
                  </ol>
                ) : (
                  <div className="muted">no decisions yet — the city is coping</div>
                )}
                <h3 style={{ marginTop: 14 }}>Elections</h3>
                <table>
                  <thead><tr><th>Election</th><th className="num">Tick</th><th>Held</th><th>Winner</th><th className="num">Turnout</th></tr></thead>
                  <tbody>
                    {(data.elections as Json[]).map((election) => (
                      <tr key={election.id}>
                        <td>{election.id}</td>
                        <td className="num muted">{election.scheduled_tick}</td>
                        <td>{election.held ? "yes" : "pending"}</td>
                        <td className="muted">{election.winner || "—"}</td>
                        <td className="num">{election.turnout ? pct(election.turnout) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        ) : null}
      </Guard>
    </>
  );
}
