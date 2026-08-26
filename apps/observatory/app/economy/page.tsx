"use client";

import { Guard, Header, useView } from "@/components/Page";
import { Spark, Stat } from "@/components/Widgets";
import { fmt, Json, money, pct } from "@/lib/api";

export default function EconomyPage() {
  const { data, error, loading } = useView<Json>("/economy", 2500);
  return (
    <>
      <Header title="Economy" right={data ? `${data.currency} · ${fmt(data.transactions, 0)} transactions` : ""} />
      <Guard loading={loading} error={error} data={data}>
        {data ? (
          <>
            <div className="grid cols-6" style={{ marginBottom: 12 }}>
              <Stat label="CPI" value={fmt(data.cpi, 3)} />
              <Stat label="Inflation (annualised)" value={pct(data.inflation_annual)} />
              <Stat label="Unemployment" value={pct(data.unemployment)} />
              <Stat label="Wage index" value={fmt(data.wage_index, 3)} />
              <Stat label="Imports" value={money(data.imports)} />
              <Stat label="Exports" value={money(data.exports)} />
            </div>

            <div className="grid cols-2">
              <div className="card">
                <h3>Markets</h3>
                <div className="scroll" style={{ maxHeight: 520 }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Good</th><th className="num">Price</th><th className="num">Unit cost</th>
                        <th className="num">Demand</th><th className="num">Stock</th><th>Trend</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data.markets as Json[]).map((market) => (
                        <tr key={market.code}>
                          <td>
                            {market.name}
                            {market.essential ? <span className="pill" style={{ marginLeft: 6 }}>essential</span> : null}
                            {market.shortage_ticks > 0 ? <span className="pill off" style={{ marginLeft: 6 }}>short</span> : null}
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
                  <h3>Sectors</h3>
                  <table>
                    <thead>
                      <tr><th>Sector</th><th className="num">Firms</th><th className="num">Jobs</th><th className="num">Output</th><th className="num">Cash</th></tr>
                    </thead>
                    <tbody>
                      {(data.sectors as Json[]).map((row) => (
                        <tr key={row.sector}>
                          <td>{row.sector}</td>
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
                  <h3>Banks</h3>
                  <table>
                    <thead>
                      <tr><th>Bank</th><th className="num">Capital</th><th className="num">Loans</th><th className="num">NPL</th><th className="num">Spread</th></tr>
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
                    outstanding {money(data.loans_outstanding)} · defaults {data.defaults}
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
