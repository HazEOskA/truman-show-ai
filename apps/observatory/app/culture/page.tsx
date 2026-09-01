"use client";

import { Guard, Header, useView } from "@/components/Page";
import { useI18n } from "@/components/I18n";
import { Bar, Stat } from "@/components/Widgets";
import { fmt, Json, pct } from "@/lib/api";

export default function CulturePage() {
  const { t, term } = useI18n();
  const { data, error, loading } = useView<Json>("/culture", 4000);
  return (
    <>
      <Header title={t("culture.title")} right={data ? t("culture.summary", { born: data.born_total, died: data.died_total }) : ""} />
      <Guard loading={loading} error={error} data={data}>
        {data ? (
          <>
            <div className="grid cols-4" style={{ marginBottom: 12 }}>
              <Stat label={t("culture.mood")} value={pct(data.mood_index)} />
              <Stat label={t("culture.living")} value={(data.trends as Json[]).filter((trend) => trend.alive).length} />
              <Stat label={t("culture.slang")} value={Object.keys(data.slang ?? {}).length} />
              <Stat label={t("culture.faded")} value={data.died_total} />
            </div>
            <div className="card">
              <h3>{t("culture.trends")}</h3>
              <table>
                <thead>
                  <tr><th>{t("culture.trend")}</th><th>{t("common.kind")}</th><th>{t("culture.driver")}</th><th>{t("culture.origin")}</th><th className="num">{t("culture.popularity")}</th>
                    <th className="num">{t("culture.adherents")}</th><th>{t("common.state")}</th></tr>
                </thead>
                <tbody>
                  {(data.trends as Json[]).map((trend) => (
                    <tr key={trend.id}>
                      <td>{trend.label}</td>
                      <td className="muted">{term(trend.kind)}</td>
                      <td className="muted">{term(trend.driver)}</td>
                      <td className="muted">{String(trend.origin_district).replace("district_", "")}</td>
                      <td className="num"><Bar value={trend.popularity} /></td>
                      <td className="num">{fmt(trend.adherents, 0)}</td>
                      <td>{trend.alive ? <span className="pill on">{t("culture.alive")}</span> : <span className="pill">{t("culture.faded")}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!(data.trends as Json[]).length ? (
                <div className="muted">
                  {t("culture.noTrends")}
                </div>
              ) : null}
            </div>
          </>
        ) : null}
      </Guard>
    </>
  );
}
