"use client";

import { Guard, Header, useView } from "@/components/Page";
import { Bar, Stat } from "@/components/Widgets";
import { fmt, Json, pct } from "@/lib/api";

export default function CulturePage() {
  const { data, error, loading } = useView<Json>("/culture", 4000);
  return (
    <>
      <Header title="Culture" right={data ? `${data.born_total} trends born · ${data.died_total} faded` : ""} />
      <Guard loading={loading} error={error} data={data}>
        {data ? (
          <>
            <div className="grid cols-4" style={{ marginBottom: 12 }}>
              <Stat label="Mood index" value={pct(data.mood_index)} />
              <Stat label="Living trends" value={(data.trends as Json[]).filter((t) => t.alive).length} />
              <Stat label="Slang terms" value={Object.keys(data.slang ?? {}).length} />
              <Stat label="Faded" value={data.died_total} />
            </div>
            <div className="card">
              <h3>Trends</h3>
              <table>
                <thead>
                  <tr><th>Trend</th><th>Kind</th><th>Driver</th><th>Origin</th><th className="num">Popularity</th>
                    <th className="num">Adherents</th><th>State</th></tr>
                </thead>
                <tbody>
                  {(data.trends as Json[]).map((trend) => (
                    <tr key={trend.id}>
                      <td>{trend.label}</td>
                      <td className="muted">{trend.kind}</td>
                      <td className="muted">{trend.driver}</td>
                      <td className="muted">{String(trend.origin_district).replace("district_", "")}</td>
                      <td className="num"><Bar value={trend.popularity} /></td>
                      <td className="num">{fmt(trend.adherents, 0)}</td>
                      <td>{trend.alive ? <span className="pill on">alive</span> : <span className="pill">faded</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!(data.trends as Json[]).length ? (
                <div className="muted">
                  Nothing has taken hold yet. Trends emerge from what the city lives through — give it time, or a shock.
                </div>
              ) : null}
            </div>
          </>
        ) : null}
      </Guard>
    </>
  );
}
