"use client";

import { Guard, Header, useView } from "@/components/Page";
import { useI18n } from "@/components/I18n";
import { Bar, Spark, Stat } from "@/components/Widgets";
import { fmt, Json, money, pct } from "@/lib/api";

export default function GovernmentPage() {
  const { t, term } = useI18n();
  const { data, error, loading } = useView<Json>("/government", 2500);
  return (
    <>
      <Header title={t("government.title")} right={data?.mayor ? t("government.mayor", { name: data.mayor.name }) : ""} />
      <Guard loading={loading} error={error} data={data}>
        {data ? (
          <>
            <div className="grid cols-6" style={{ marginBottom: 12 }}>
              <Stat label={t("government.approval")} value={pct(data.approval)} tone={data.approval < 0.35 ? "bad" : "good"} />
              <Stat label={t("government.unrest")} value={pct(data.unrest_index)} tone={data.unrest_index > 0.3 ? "bad" : undefined} />
              <Stat label={t("government.emergency")} value={term(data.emergency_level)} tone={data.emergency_level ? "warn" : undefined} />
              <Stat label={t("government.treasury")} value={money(data.treasury)} />
              <Stat label={t("government.debt")} value={money(data.debt)} />
              <Stat label={t("government.publicJobs")} value={fmt(data.public_jobs, 0)} />
            </div>

            <div className="grid cols-2">
              <div className="card">
                <h3>{t("government.approvalHistory")}</h3>
                <Spark points={(data.approval_history ?? []) as number[]} width={460} height={70} colour="var(--good)" />
                <h3 style={{ marginTop: 14 }}>{t("government.parties")}</h3>
                <table>
                  <thead><tr><th>{t("government.party")}</th><th>{t("government.leader")}</th><th className="num">{t("government.support")}</th><th className="num">{t("government.seats")}</th></tr></thead>
                  <tbody>
                    {(data.parties as Json[]).map((party) => (
                      <tr key={party.id}>
                        <td>{party.name} {party.in_power ? <span className="pill on">{t("government.inPower")}</span> : null}</td>
                        <td className="muted">{party.leader || "—"}</td>
                        <td className="num"><Bar value={party.support} /></td>
                        <td className="num">{party.seats}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="card">
                <h3>{t("government.policies")}</h3>
                <div className="scroll">
                  <table>
                    <thead>
                      <tr><th>{t("government.policy")}</th><th>{t("government.target")}</th><th className="num">{t("government.value")}</th><th className="num">{t("government.costDay")}</th><th className="num">{t("government.enacted")}</th><th>{t("common.state")}</th></tr>
                    </thead>
                    <tbody>
                      {(data.policies as Json[]).map((policy) => (
                        <tr key={policy.id}>
                          <td>{term(policy.kind)}</td>
                          <td className="muted">{policy.target ? term(policy.target) : "—"}</td>
                          <td className="num">{fmt(policy.value, 3)}</td>
                          <td className="num">{money(policy.cost_per_day)}</td>
                          <td className="num muted">t{policy.enacted_tick}</td>
                          <td>{policy.active ? <span className="pill on">{t("government.active")}</span> : <span className="pill">{t("government.expired")}</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="card">
                <h3>{t("government.institutions")}</h3>
                <table>
                  <thead><tr><th>{t("government.institution")}</th><th>{t("government.leader")}</th><th className="num">{t("government.staff")}</th><th className="num">{t("government.budget")}</th><th className="num">{t("government.effectiveness")}</th></tr></thead>
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
                <h3>{t("government.log")}</h3>
                {(data.decision_log as string[]).length ? (
                  <ol style={{ margin: 0, paddingLeft: 18 }}>
                    {(data.decision_log as string[]).slice().reverse().map((line, index) => (
                      <li key={index} className="muted">{line}</li>
                    ))}
                  </ol>
                ) : (
                  <div className="muted">{t("government.noDecisions")}</div>
                )}
                <h3 style={{ marginTop: 14 }}>{t("government.elections")}</h3>
                <table>
                  <thead><tr><th>{t("government.election")}</th><th className="num">{t("common.tick")}</th><th>{t("government.held")}</th><th>{t("government.winner")}</th><th className="num">{t("government.turnout")}</th></tr></thead>
                  <tbody>
                    {(data.elections as Json[]).map((election) => (
                      <tr key={election.id}>
                        <td>{election.id}</td>
                        <td className="num muted">{election.scheduled_tick}</td>
                        <td>{election.held ? t("common.yes") : t("government.pending")}</td>
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
