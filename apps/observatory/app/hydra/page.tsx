"use client";

import { Guard, Header, useView } from "@/components/Page";
import { useI18n } from "@/components/I18n";
import { Bar } from "@/components/Widgets";
import { fmt, Json, pct } from "@/lib/api";

export default function HydraPage() {
  const { t, term } = useI18n();
  const { data, error, loading } = useView<Json>("/city", 2000);
  return (
    <>
      <Header title={t("hydra.title")} right={data ? t("hydra.summary", { name: data.city?.name, year: data.city?.founded_year }) : ""} />
      <Guard loading={loading} error={error} data={data}>
        {data ? (
          <>
            <div className="grid cols-3" style={{ marginBottom: 12 }}>
              <div className="card">
                <h3>{t("hydra.infrastructure")}</h3>
                <table>
                  <tbody>
                    <tr><td>{t("hydra.powerOutput")}</td><td className="num">{fmt(data.city.infrastructure.power_output_mw, 1)} MW</td></tr>
                    <tr><td>{t("hydra.powerDemand")}</td><td className="num">{fmt(data.city.infrastructure.power_demand_mw, 1)} MW</td></tr>
                    <tr><td>{t("hydra.capacity")}</td><td className="num">{fmt(data.city.infrastructure.power_capacity_mw, 1)} MW</td></tr>
                    <tr><td>{t("hydra.waterOutput")}</td><td className="num">{fmt(data.city.infrastructure.water_output_m3, 0)} m³/d</td></tr>
                    <tr><td>{t("hydra.roadLoad")}</td><td className="num">{fmt(data.city.infrastructure.road_load, 2)}</td></tr>
                    <tr><td>{t("hydra.condition")}</td><td className="num">{pct(data.city.infrastructure.condition)}</td></tr>
                  </tbody>
                </table>
              </div>
              <div className="card">
                <h3>{t("hydra.weather")}</h3>
                <table>
                  <tbody>
                    <tr><td>{t("hydra.temperature")}</td><td className="num">{fmt(data.city.weather.temperature_c, 1)} °C</td></tr>
                    <tr><td>{t("hydra.season")}</td><td className="num">{term(data.city.weather.season)}</td></tr>
                    <tr><td>{t("hydra.rain")}</td><td className="num">{fmt(data.city.weather.precipitation_mm, 1)} mm</td></tr>
                    <tr><td>{t("hydra.wind")}</td><td className="num">{fmt(data.city.weather.wind_kph, 0)} kph</td></tr>
                    <tr><td>{t("hydra.region")}</td><td className="num">{data.region.name}</td></tr>
                    <tr><td>{t("hydra.stability")}</td><td className="num">{pct(data.region.political_stability)}</td></tr>
                  </tbody>
                </table>
              </div>
              <div className="card">
                <h3>{t("hydra.housing")}</h3>
                <table>
                  <tbody>
                    <tr><td>{t("hydra.households")}</td><td className="num">{fmt(data.housing.households, 0)}</td></tr>
                    <tr><td>{t("hydra.capacityHousing")}</td><td className="num">{fmt(data.housing.dwelling_capacity, 0)}</td></tr>
                    <tr><td>{t("hydra.arrears")}</td><td className="num">{fmt(data.housing.homeless_households, 0)}</td></tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div className="grid cols-2">
              <div className="card">
                <h3>{t("hydra.districts")}</h3>
                <div className="scroll">
                  <table>
                    <thead>
                      <tr><th>{t("hydra.district")}</th><th>{t("common.kind")}</th><th className="num">{t("hydra.population")}</th><th className="num">{t("hydra.wealth")}</th>
                        <th className="num">{t("hydra.unrest")}</th><th className="num">{t("hydra.power")}</th><th className="num">{t("hydra.crime")}</th></tr>
                    </thead>
                    <tbody>
                      {(data.districts as Json[]).map((d) => (
                        <tr key={d.id}>
                          <td>{d.name}</td>
                          <td className="muted">{term(d.kind)}</td>
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
                <h3>{t("hydra.plants")}</h3>
                <table>
                  <thead>
                    <tr><th>{t("hydra.plant")}</th><th>{t("hydra.fuel")}</th><th className="num">{t("hydra.capacity")}</th><th className="num">{t("hydra.output")}</th>
                      <th className="num">{t("hydra.availability")}</th><th>{t("hydra.operator")}</th></tr>
                  </thead>
                  <tbody>
                    {(data.power_plants as Json[]).map((p) => (
                      <tr key={p.id}>
                        <td>{p.id}</td>
                        <td className="muted">{term(p.fuel)}</td>
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
