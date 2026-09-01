"use client";

import { Guard, Header, useView } from "@/components/Page";
import { useI18n } from "@/components/I18n";
import { Bar } from "@/components/Widgets";
import { fmt, Json, money, pct } from "@/lib/api";

export default function CompaniesPage() {
  const { t, term } = useI18n();
  const { data, error, loading } = useView<Json>("/companies?limit=200", 3000);
  return (
    <>
      <Header
        title={t("companies.title")}
        right={data ? t("companies.summary", { active: data.total, bankruptcies: data.bankruptcies, jobs: fmt(data.total_employment, 0) }) : ""}
      />
      <Guard loading={loading} error={error} data={data}>
        <div className="card">
          <div className="scroll" style={{ maxHeight: 620 }}>
            <table>
              <thead>
                <tr>
                  <th>{t("companies.company")}</th><th>{t("companies.sector")}</th><th>{t("people.district")}</th><th className="num">{t("companies.staff")}</th>
                  <th className="num">{t("companies.target")}</th><th className="num">{t("companies.utilisation")}</th><th className="num">{t("companies.price")}</th>
                  <th className="num">{t("companies.unitCost")}</th><th className="num">{t("companies.margin")}</th><th className="num">{t("companies.cash")}</th>
                  <th>{t("companies.strategy")}</th><th className="num">{t("companies.layoffs")}</th>
                </tr>
              </thead>
              <tbody>
                {((data?.companies ?? []) as Json[]).map((company) => (
                  <tr key={company.id}>
                    <td>{company.name}</td>
                    <td className="muted">{term(company.sector)}</td>
                    <td className="muted">{String(company.district).replace("district_", "")}</td>
                    <td className="num">{fmt(company.headcount, 0)}</td>
                    <td className="num muted">{fmt(company.headcount_target, 0)}</td>
                    <td className="num"><Bar value={company.utilisation} /></td>
                    <td className="num">{money(company.price)}</td>
                    <td className="num muted">{money(company.unit_cost)}</td>
                    <td className={`num ${company.margin < 0 ? "bad" : company.margin > 0.15 ? "good" : ""}`}>
                      {pct(company.margin)}
                    </td>
                    <td className="num">{money(company.cash)}</td>
                    <td className="muted">{term(company.strategy)}</td>
                    <td className={`num ${company.layoffs_total ? "warn" : "muted"}`}>{company.layoffs_total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Guard>
    </>
  );
}
