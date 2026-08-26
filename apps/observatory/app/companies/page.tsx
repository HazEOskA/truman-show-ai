"use client";

import { Guard, Header, useView } from "@/components/Page";
import { Bar } from "@/components/Widgets";
import { fmt, Json, money, pct } from "@/lib/api";

export default function CompaniesPage() {
  const { data, error, loading } = useView<Json>("/companies?limit=200", 3000);
  return (
    <>
      <Header
        title="Companies"
        right={data ? `${data.total} active · ${data.bankruptcies} bankruptcies · ${fmt(data.total_employment, 0)} jobs` : ""}
      />
      <Guard loading={loading} error={error} data={data}>
        <div className="card">
          <div className="scroll" style={{ maxHeight: 620 }}>
            <table>
              <thead>
                <tr>
                  <th>Company</th><th>Sector</th><th>District</th><th className="num">Staff</th>
                  <th className="num">Target</th><th className="num">Util.</th><th className="num">Price</th>
                  <th className="num">Unit cost</th><th className="num">Margin</th><th className="num">Cash</th>
                  <th>Strategy</th><th className="num">Layoffs</th>
                </tr>
              </thead>
              <tbody>
                {((data?.companies ?? []) as Json[]).map((company) => (
                  <tr key={company.id}>
                    <td>{company.name}</td>
                    <td className="muted">{company.sector}</td>
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
                    <td className="muted">{company.strategy}</td>
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
