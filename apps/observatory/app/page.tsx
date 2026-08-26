"use client";

import { useEffect, useState } from "react";
import Controls from "@/components/Controls";
import WorldPicker from "@/components/WorldPicker";
import { Spark, Stat } from "@/components/Widgets";
import { apiGet, fmt, Json, pct, usePolling, useSelection } from "@/lib/api";

export default function WorldPage() {
  const { worldId, timelineId, select } = useSelection();
  const base = worldId ? `/worlds/${worldId}/timelines/${timelineId}` : null;
  const { data: state } = usePolling<Json>(base ? `${base}/state` : null, 1500);
  const { data: telemetry } = usePolling<Json>(base ? `${base}/telemetry?limit=240` : null, 3000);
  const [control, setControl] = useState<Json | null>(null);

  async function refreshControl() {
    if (!base) return;
    try {
      setControl(await apiGet<Json>(`${base}/control`));
    } catch {
      setControl(null);
    }
  }

  useEffect(() => {
    refreshControl();
    const timer = setInterval(refreshControl, 2000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base]);

  const series = (key: string): number[] =>
    ((telemetry?.telemetry ?? []) as Json[]).map((row) => Number(row.metrics?.[key] ?? 0));

  return (
    <>
      <div className="topbar">
        <h2>World</h2>
        <div className="clock">
          {state ? `${state.sim_time} · tick ${state.tick}` : "no world running"}
        </div>
      </div>

      <div className="grid cols-2" style={{ marginBottom: 12 }}>
        <WorldPicker worldId={worldId} timelineId={timelineId} onSelect={select} />
        <Controls worldId={worldId} timelineId={timelineId} control={control} onChanged={refreshControl} />
      </div>

      {!state ? (
        <div className="card">
          <p className="muted">
            No world selected. Choose a seed and press <strong>Genesis</strong> to create one, then press
            <strong> Run</strong>.
          </p>
        </div>
      ) : (
        <>
          <div className="grid cols-6" style={{ marginBottom: 12 }}>
            <Stat label="Population" value={fmt(state.population, 0)} hint={`${state.individuals} simulated individually`} />
            <Stat label="Companies" value={state.companies} hint={`${state.persistent_agents} persistent agents`} />
            <Stat label="Unemployment" value={pct(state.economy?.unemployment)} tone={state.economy?.unemployment > 0.1 ? "bad" : "good"} />
            <Stat label="CPI" value={fmt(state.economy?.cpi, 3)} hint={`inflation ${pct(state.economy?.inflation_annual)}`} />
            <Stat label="Energy price" value={`${fmt(state.economy?.energy_price, 0)} minor/kWh`} />
            <Stat
              label="Approval"
              value={pct(state.government?.approval)}
              hint={`unrest ${pct(state.government?.unrest)}`}
              tone={state.government?.approval < 0.35 ? "bad" : undefined}
            />
          </div>

          <div className="grid cols-3">
            <div className="card">
              <h3>Grid</h3>
              <div>
                output <strong>{fmt(state.city?.power_output_mw, 1)} MW</strong> / demand{" "}
                {fmt(state.city?.power_demand_mw, 1)} MW
              </div>
              <div className="muted">capacity {fmt(state.city?.power_capacity_mw, 1)} MW</div>
              <Spark points={series("power_output_mw")} />
            </div>
            <div className="card">
              <h3>Consumer prices</h3>
              <Spark points={series("cpi")} colour="var(--warn)" />
              <div className="muted">energy price</div>
              <Spark points={series("energy_price")} colour="var(--bad)" />
            </div>
            <div className="card">
              <h3>Agent activity</h3>
              <table>
                <tbody>
                  {Object.entries(state.activity ?? {}).map(([key, value]) => (
                    <tr key={key}>
                      <td>{key}</td>
                      <td className="num">{fmt(Number(value), 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card">
              <h3>Identity</h3>
              <table>
                <tbody>
                  <tr><td>seed</td><td className="num">{state.seed}</td></tr>
                  <tr><td>kernel</td><td className="num">{state.kernel_version}</td></tr>
                  <tr><td>config hash</td><td className="num">{String(state.config_hash).slice(0, 12)}</td></tr>
                  <tr><td>state hash</td><td className="num">{String(state.state_hash).slice(0, 12)}</td></tr>
                  <tr><td>phase</td><td className="num">{state.phase}</td></tr>
                  <tr><td>timeline</td><td className="num">{state.timeline_id}</td></tr>
                </tbody>
              </table>
            </div>
            <div className="card">
              <h3>Compute cost</h3>
              <table>
                <tbody>
                  <tr><td>agent decisions / tick</td><td className="num">{fmt(state.metrics?.agent_ticks, 0)}</td></tr>
                  <tr><td>sleeping agents</td><td className="num">{fmt(state.metrics?.sleeping_agents, 0)}</td></tr>
                  <tr><td>LLM calls</td><td className="num">{fmt(state.metrics?.llm_calls, 0)}</td></tr>
                  <tr><td>tokens used</td><td className="num">{fmt(state.metrics?.tokens_used, 0)}</td></tr>
                  <tr><td>events / tick</td><td className="num">{fmt(state.metrics?.events_emitted, 0)}</td></tr>
                  <tr><td>tick time</td><td className="num">{fmt(state.metrics?.tick_ms, 1)} ms</td></tr>
                </tbody>
              </table>
            </div>
            <div className="card">
              <h3>Unrest &amp; approval</h3>
              <Spark points={series("unrest_index")} colour="var(--bad)" />
              <Spark points={series("gov_approval")} colour="var(--good)" />
            </div>
          </div>
        </>
      )}
    </>
  );
}
