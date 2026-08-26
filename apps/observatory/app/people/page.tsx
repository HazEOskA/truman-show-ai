"use client";

import Link from "next/link";
import { useState } from "react";
import { Guard, Header, useView } from "@/components/Page";
import { fmt, Json, money, pct, useSelection } from "@/lib/api";

export default function PeoplePage() {
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
      <Header title="People" right={data ? `${fmt(data.total, 0)} individually simulated` : ""} />
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="row">
          <button className={tier === "" ? "primary" : ""} onClick={() => setTier("")}>All</button>
          <button className={tier === "A" ? "primary" : ""} onClick={() => setTier("A")}>Tier A — persistent</button>
          <button className={tier === "B" ? "primary" : ""} onClick={() => setTier("B")}>Tier B — lightweight</button>
          <input placeholder="name or occupation" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
      </div>
      <Guard loading={loading} error={error} data={data}>
        <div className="card">
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Name</th><th>Tier</th><th className="num">Age</th><th>District</th><th>Occupation</th>
                  <th>Status</th><th className="num">Wealth</th><th className="num">Energy</th>
                  <th className="num">Stress</th><th className="num">Trust</th><th>Activity</th>
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
                    <td>{person.occupation}</td>
                    <td className={person.employment === "unemployed" ? "bad" : "muted"}>{person.employment}</td>
                    <td className="num">{money(person.wealth)}</td>
                    <td className="num">{pct(person.energy, 0)}</td>
                    <td className={`num ${person.stress > 0.6 ? "warn" : ""}`}>{pct(person.stress, 0)}</td>
                    <td className="num">{pct(person.political_trust, 0)}</td>
                    <td className="muted">{person.activity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Guard>
      <p className="muted" style={{ marginTop: 10 }}>
        world {worldId || "—"} · timeline {timelineId}
      </p>
    </>
  );
}
