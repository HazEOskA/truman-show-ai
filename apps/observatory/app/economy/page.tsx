"use client";

import { Guard, Header, useView } from "@/components/Page";
import { useI18n } from "@/components/I18n";
import { Spark, Stat } from "@/components/Widgets";
import { fmt, Json, money, pct } from "@/lib/api";

export default function EconomyPage() {
  const { t, term } = useI18n();
  const { data, error, loading } = useView<Json>("/economy", 2500);
  return (
    <>
      <Header title={t("economy.title")} right={data ? t("economy.summary", { currency: data.currency, count: fmt(data.transactions, 0) }) : ""} />
      <Guard loading={loading} error={error} data={data}>
        {data ? (
          <>
            <div className="grid cols-6" style={{ marginBottom: 12 }}>
              <Stat label="CPI" value={fmt(data.cpi, 3)} />
              <Stat label={t("economy.inflation")} value={pct(data.inflation_annual)} />
              <Stat label={t("economy.unemployment")} value={pct(data.unemployment)} />
              <Stat label={t("economy.wageIndex")} value={fmt(data.wage_index, 3)} />
              <Stat label={t("economy.imports")} value={money(data.imports)} />
              <Stat label={t("economy.exports")} value={money(data.exports)} />
            </div>

            <div className="grid cols-2">
              <div className="card">
                <h3>{t("economy.markets")}</h3>
                <div className="scroll" style={{ maxHeight: 520 }}>
                  <table>
                    <thead>
                      <tr>
                        <th>{t("economy.good")}</th><th className="num">{t("economy.price")}</th><th className="num">{t("economy.unitCost")}</th>
                        <th className="num">{t("economy.demand")}</th><th className="num">{t("economy.stock")}</th><th>{t("economy.trend")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data.markets as Json[]).map((market) => (
                        <tr key={market.code}>
                          <td>
                            {term(market.name)}
                            {market.essential ? <span className="pill" style={{ marginLeft: 6 }}>{t("economy.essential")}</span> : null}
                            {market.shortage_ticks > 0 ? <span className="pill off" style={{ marginLeft: 6 }}>{t("economy.short")}</span> : null}
                          </td>
                          <td className="num">{market.price_minor}</td>
                          <td className="num muted">{fmt(market.unit_cost * 100, 0)}</td>
                          <td className="num">{fmt(market.last_demand, 0)}</td>
                          <td className="num">{fmt(market.inventory, 0)}</td>
                          <td><Spark points={market.history as number[]} width={130} height={26} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div>
                <div className="card" style={{ marginBottom: 12 }}>
                  <h3>{t("economy.sectors")}</h3>
                  <table>
                    <thead>
                      <tr><th>{t("economy.sector")}</th><th className="num">{t("economy.firms")}</th><th className="num">{t("economy.jobs")}</th><th className="num">{t("economy.output")}</th><th className="num">{t("economy.cash")}</th></tr>
                    </thead>
                    <tbody>
                      {(data.sectors as Json[]).map((row) => (
                        <tr key={row.sector}>
                          <td>{term(row.sector)}</td>
                          <td className="num">{row.companies}</td>
                          <td className="num">{fmt(row.employment, 0)}</td>
                          <td className="num">{fmt(row.output, 0)}</td>
                          <td className="num">{money(row.cash)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="card">
                  <h3>{t("economy.banks")}</h3>
                  <table>
                    <thead>
                      <tr><th>{t("economy.bank")}</th><th className="num">{t("economy.capital")}</th><th className="num">{t("economy.loans")}</th><th className="num">{t("economy.npl")}</th><th className="num">{t("economy.spread")}</th></tr>
                    </thead>
                    <tbody>
                      {(data.banks as Json[]).map((bank) => (
                        <tr key={bank.id}>
                          <td>{bank.name}</td>
                          <td className="num">{money(bank.capital)}</td>
                          <td className="num">{money(bank.loans)}</td>
                          <td className={`num ${bank.npl > 0 ? "warn" : "muted"}`}>{money(bank.npl)}</td>
                          <td className="num">{pct(bank.spread)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="muted" style={{ marginTop: 8 }}>
                    {t("economy.outstanding", { value: money(data.loans_outstanding), defaults: data.defaults })}
                  </div>
                </div>
              </div>
            </div>
          </>
        ) : null}
      </Guard>
    </>
  );
}
