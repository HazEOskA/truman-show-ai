"use client";

import { Guard, Header, useView } from "@/components/Page";
import { Bar } from "@/components/Widgets";
import { fmt, Json, pct } from "@/lib/api";

export default function HydraPage() {
  const { data, error, loading } = useView<Json>("/city", 2000);
  return (
    <>
      <Header title="Hydra" right={data ? `${data.city?.name} · founded ${data.city?.founded_year}` : ""} />
      <Guard loading={loading} error={error} data={data}>
        {data ? (
          <>
            <div className="grid cols-3" style={{ marginBottom: 12 }}>
              <div className="card">
                <h3>Infrastructure</h3>
                <table>
                  <tbody>
                    <tr><td>power output</td><td className="num">{fmt(data.city.infrastructure.power_output_mw, 1)} MW</td></tr>
                    <tr><td>power demand</td><td className="num">{fmt(data.city.infrastructure.power_demand_mw, 1)} MW</td></tr>
                    <tr><td>capacity</td><td className="num">{fmt(data.city.infrastructure.power_capacity_mw, 1)} MW</td></tr>
                    <tr><td>water output</td><td className="num">{fmt(data.city.infrastructure.water_output_m3, 0)} m³/d</td></tr>
                    <tr><td>road load</td><td className="num">{fmt(data.city.infrastructure.road_load, 2)}</td></tr>
                    <tr><td>condition</td><td className="num">{pct(data.city.infrastructure.condition)}</td></tr>
                  </tbody>
                </table>
              </div>
              <div className="card">
                <h3>Weather &amp; region</h3>
                <table>
                  <tbody>
                    <tr><td>temperature</td><td className="num">{fmt(data.city.weather.temperature_c, 1)} °C</td></tr>
                    <tr><td>season</td><td className="num">{data.city.weather.season}</td></tr>
                    <tr><td>rain</td><td className="num">{fmt(data.city.weather.precipitation_mm, 1)} mm</td></tr>
                    <tr><td>wind</td><td className="num">{fmt(data.city.weather.wind_kph, 0)} kph</td></tr>
                    <tr><td>region</td><td className="num">{data.region.name}</td></tr>
                    <tr><td>stability</td><td className="num">{pct(data.region.political_stability)}</td></tr>
                  </tbody>
                </table>
              </div>
              <div className="card">
                <h3>Housing</h3>
                <table>
                  <tbody>
                    <tr><td>households (simulated)</td><td className="num">{fmt(data.housing.households, 0)}</td></tr>
                    <tr><td>dwelling capacity</td><td className="num">{fmt(data.housing.dwelling_capacity, 0)}</td></tr>
                    <tr><td>households in arrears</td><td className="num">{fmt(data.housing.homeless_households, 0)}</td></tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div className="grid cols-2">
              <div className="card">
                <h3>Districts</h3>
                <div className="scroll">
                  <table>
                    <thead>
                      <tr><th>District</th><th>Kind</th><th className="num">Pop</th><th className="num">Wealth</th>
                        <th className="num">Unrest</th><th className="num">Power</th><th className="num">Crime</th></tr>
                    </thead>
                    <tbody>
                      {(data.districts as Json[]).map((d) => (
                        <tr key={d.id}>
                          <td>{d.name}</td>
                          <td className="muted">{d.kind}</td>
                          <td className="num">{fmt(d.population, 0)}</td>
                          <td className="num"><Bar value={d.wealth_index} /></td>
                          <td className="num">{pct(d.unrest)}</td>
                          <td className="num">{pct(d.power_reliability)}</td>
                          <td className="num">{pct(d.crime_rate, 2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="card">
                <h3>Power plants</h3>
                <table>
                  <thead>
                    <tr><th>Plant</th><th>Fuel</th><th className="num">Capacity</th><th className="num">Output</th>
                      <th className="num">Availability</th><th>Operator</th></tr>
                  </thead>
                  <tbody>
                    {(data.power_plants as Json[]).map((p) => (
                      <tr key={p.id}>
                        <td>{p.id}</td>
                        <td className="muted">{p.fuel}</td>
                        <td className="num">{fmt(p.capacity_mw, 1)} MW</td>
                        <td className="num">{fmt(p.output_mw, 1)} MW</td>
                        <td className={`num ${p.availability < 0.95 ? "bad" : ""}`}>{pct(p.availability)}</td>
                        <td className="muted">{p.operator}</td>
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
