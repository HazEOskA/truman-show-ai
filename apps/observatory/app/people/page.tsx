"use client";

import Link from "next/link";
import { useState } from "react";
import { Guard, Header, useView } from "@/components/Page";
import { useI18n } from "@/components/I18n";
import { fmt, Json, money, pct, useSelection } from "@/lib/api";

export default function PeoplePage() {
  const { t, term } = useI18n();
  const [tier, setTier] = useState("");
  const [query, setQuery] = useState("");
  const { timelineId } = useSelection();
  const { data, error, loading } = useView<Json>(
    `/people?limit=200&tier=${tier}&q=${encodeURIComponent(query)}`,
    3000
  );
  const { worldId } = useSelection();

  return (
    <>
      <Header title={t("people.title")} right={data ? t("people.simulated", { count: fmt(data.total, 0) }) : ""} />
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="row">
          <button className={tier === "" ? "primary" : ""} onClick={() => setTier("")}>{t("people.tierAll")}</button>
          <button className={tier === "A" ? "primary" : ""} onClick={() => setTier("A")}>{t("people.tierA")}</button>
          <button className={tier === "B" ? "primary" : ""} onClick={() => setTier("B")}>{t("people.tierB")}</button>
          <input placeholder={t("people.search")} aria-label={t("people.search")} value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
      </div>
      <Guard loading={loading} error={error} data={data}>
        <div className="card">
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>{t("people.name")}</th><th>{t("people.tier")}</th><th className="num">{t("people.age")}</th><th>{t("people.district")}</th><th>{t("people.occupation")}</th>
                  <th>{t("people.status")}</th><th className="num">{t("people.wealth")}</th><th className="num">{t("people.energy")}</th>
                  <th className="num">{t("people.stress")}</th><th className="num">{t("people.trust")}</th><th>{t("people.activity")}</th>
                </tr>
              </thead>
              <tbody>
                {((data?.people ?? []) as Json[]).map((person) => (
                  <tr key={person.id}>
                    <td>
                      <Link href={`/people/${person.id}`}>{person.name}</Link>
                    </td>
                    <td className="muted">{person.tier}</td>
                    <td className="num">{fmt(person.age, 0)}</td>
                    <td className="muted">{String(person.district).replace("district_", "")}</td>
                    <td>{term(person.occupation)}</td>
                    <td className={person.employment === "unemployed" ? "bad" : "muted"}>{term(person.employment)}</td>
                    <td className="num">{money(person.wealth)}</td>
                    <td className="num">{pct(person.energy, 0)}</td>
                    <td className={`num ${person.stress > 0.6 ? "warn" : ""}`}>{pct(person.stress, 0)}</td>
                    <td className="num">{pct(person.political_trust, 0)}</td>
                    <td className="muted">{term(person.activity)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Guard>
      <p className="muted" style={{ marginTop: 10 }}>
        {t("common.worldTimeline", { world: worldId || "—", timeline: timelineId })}
      </p>
    </>
  );
}
