"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import Controls from "@/components/Controls";
import WorldPicker from "@/components/WorldPicker";
import { Spark } from "@/components/Widgets";
import { apiGet, fmt, Json, pct, usePolling, useSelection } from "@/lib/api";

type Accent = "cyan" | "violet" | "magenta" | "amber" | "green" | "blue";

const MODULES: { href: string; code: string; title: string; copy: string; accent: Accent }[] = [
  { href: "/city", code: "CITY/02", title: "Read the city", copy: "664 buildings, 928 streets and every live layer.", accent: "cyan" },
  { href: "/people", code: "LIFE/05", title: "Follow a life", copy: "Goals, memory, employment and individual consequences.", accent: "violet" },
  { href: "/economy", code: "ECON/07", title: "Watch the markets", copy: "Prices, shortages, labour and energy pressure.", accent: "amber" },
  { href: "/causal", code: "WHY/13", title: "Explain a consequence", copy: "Trace immutable events back through the causal graph.", accent: "magenta" },
  { href: "/events", code: "LOG/12", title: "Open the ledger", copy: "Every material decision, shock and state transition.", accent: "green" },
  { href: "/hydra", code: "CORE/01", title: "Inspect Hydra", copy: "Persistent agents, sleeping minds and compute cost.", accent: "blue" }
];

function MetricCard({
  label,
  value,
  hint,
  accent,
  index
}: {
  label: string;
  value: string | number;
  hint: string;
  accent: Accent;
  index: string;
}) {
  return (
    <article className="metric-card" data-accent={accent}>
      <div className="metric-topline">
        <span>{index}</span>
        <i aria-hidden="true" />
      </div>
      <div className="metric-label">{label}</div>
      <strong>{value}</strong>
      <small>{hint}</small>
    </article>
  );
}

function PanelHeader({ eyebrow, title, meta }: { eyebrow: string; title: string; meta?: string }) {
  return (
    <header className="panel-header">
      <div>
        <span>{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      {meta ? <small>{meta}</small> : null}
    </header>
  );
}

function WorldCore({ state, running }: { state: Json | null; running: boolean }) {
  const demand = Number(state?.city?.power_demand_mw ?? 0);
  const capacity = Number(state?.city?.power_capacity_mw ?? 0);
  const reserve = Math.max(0, capacity - demand);

  return (
    <div className="world-core" aria-label="Hydra world core status">
      <div className="core-grid" aria-hidden="true" />
      <div className="core-orbit core-orbit--outer" aria-hidden="true"><i /><i /><i /></div>
      <div className="core-orbit core-orbit--inner" aria-hidden="true"><i /><i /></div>
      <div className={running ? "core-node is-live" : "core-node"}>
        <span>WORLD CORE</span>
        <strong>{state ? fmt(reserve, 1) : "—"}</strong>
        <small>MW RESERVE</small>
      </div>
      <div className="core-coordinate core-coordinate--top">Y0 / TL-ZERO</div>
      <div className="core-coordinate core-coordinate--bottom">DETERMINISTIC STATE</div>
    </div>
  );
}

function ModuleLink({ module }: { module: (typeof MODULES)[number] }) {
  return (
    <Link href={module.href} className="module-link" data-accent={module.accent}>
      <span className="module-code">{module.code}</span>
      <strong>{module.title}</strong>
      <p>{module.copy}</p>
      <span className="module-open">OPEN MODULE <b aria-hidden="true">↗</b></span>
    </Link>
  );
}

function SyncState({ worldId, error }: { worldId: string; error: string | null }) {
  if (error) {
    return (
      <div className="dashboard-state dashboard-state--error">
        <span>WORLD LINK INTERRUPTED</span>
        <strong>{error}</strong>
        <small>The control surface will reconnect automatically.</small>
      </div>
    );
  }
  return (
    <div className="dashboard-state">
      <span className="sync-loader" aria-hidden="true" />
      <strong>{worldId ? "SYNCHRONIZING WORLD STATE" : "NO WORLD SELECTED"}</strong>
      <small>{worldId ? "Reading the sealed state from Hydra…" : "Choose an existing world or create one in the control deck."}</small>
    </div>
  );
}

export default function WorldPage() {
  const { worldId, timelineId, select } = useSelection();
  const base = worldId ? `/worlds/${worldId}/timelines/${timelineId}` : null;
  const { data: state, error: stateError } = usePolling<Json>(base ? `${base}/state` : null, 1500);
  const { data: telemetry } = usePolling<Json>(base ? `${base}/telemetry?limit=240` : null, 3000);
  const { data: ledger } = usePolling<Json>(base ? `${base}/events?limit=6&min_importance=0` : null, 4000);
  const [control, setControl] = useState<Json | null>(null);

  const refreshControl = useCallback(async () => {
    if (!base) return;
    try {
      setControl(await apiGet<Json>(`${base}/control`));
    } catch {
      setControl(null);
    }
  }, [base]);

  useEffect(() => {
    refreshControl();
    const timer = setInterval(refreshControl, 2000);
    return () => clearInterval(timer);
  }, [refreshControl]);

  const telemetryRows = useMemo(() => (telemetry?.telemetry ?? []) as Json[], [telemetry]);
  const series = (key: string): number[] => telemetryRows.map((row) => Number(row.metrics?.[key] ?? 0));
  const events = (ledger?.events ?? []) as Json[];
  const activity = Object.entries(state?.activity ?? {}).sort((a, b) => Number(b[1]) - Number(a[1])).slice(0, 6);
  const running = control?.mode === "running";
  const powerDemand = Number(state?.city?.power_demand_mw ?? 0);
  const powerCapacity = Number(state?.city?.power_capacity_mw ?? 0);
  const powerShare = powerCapacity ? Math.min(100, (powerDemand / powerCapacity) * 100) : 0;
  const observedShare = state?.population ? Number(state.individuals ?? 0) / Number(state.population) : 0;

  return (
    <div className="command-center">
      <section className="command-hero">
        <div className="hero-atmosphere" aria-hidden="true" />
        <div className="hero-copy">
          <div className="command-kicker">
            <span className={running ? "live-beacon is-live" : "live-beacon"} />
            OSA TECH // LIVE CIVILIZATION ENGINE
          </div>
          <h1>
            THE CITY<br />
            <span>IS ALIVE.</span>
          </h1>
          <p>
            Hydra is a deterministic society where people remember, institutions react and every
            consequence leaves proof. This is its command surface.
          </p>
          <div className="hero-actions">
            <Link href="/city" className="action action--primary">ENTER CITY VIEW <span>↗</span></Link>
            <Link href="/causal" className="action">TRACE A CONSEQUENCE <span>→</span></Link>
          </div>
          <div className="hero-proof">
            <span><b>01</b> NO MOCK DATA</span>
            <span><b>02</b> SEALED TIMELINES</span>
            <span><b>03</b> CAUSAL PROOF</span>
          </div>
        </div>

        <WorldCore state={state} running={running} />

        <div className="hero-telemetry">
          <div><span>WORLD</span><strong>{state?.city?.name ?? "HYDRA"}</strong></div>
          <div><span>SIM TIME</span><strong>{state?.sim_time ?? "SYNCING"}</strong></div>
          <div><span>MODE</span><strong className={running ? "good" : "warn"}>{running ? "RUNNING" : "PAUSED"}</strong></div>
          <div><span>STATE</span><strong>{state?.phase ?? "—"}</strong></div>
        </div>
      </section>

      <section className="control-deck" aria-label="World control deck">
        <div className="section-intro">
          <span>CONTROL DECK / 01</span>
          <h2>Select the world. Control time. Inject pressure.</h2>
        </div>
        <div className="control-grid">
          <WorldPicker worldId={worldId} timelineId={timelineId} onSelect={select} variant="command" />
          <Controls worldId={worldId} timelineId={timelineId} control={control} onChanged={refreshControl} />
        </div>
      </section>

      {!state ? (
        <SyncState worldId={worldId} error={stateError} />
      ) : (
        <>
          <section className="metrics-grid" aria-label="World metrics">
            <MetricCard index="01" label="Population" value={fmt(state.population, 0)} hint={`${fmt(state.individuals, 0)} individually simulated`} accent="cyan" />
            <MetricCard index="02" label="Persistent minds" value={fmt(state.persistent_agents, 0)} hint="Agents with memory and goals" accent="violet" />
            <MetricCard index="03" label="Companies" value={fmt(state.companies, 0)} hint="Competing economic actors" accent="blue" />
            <MetricCard index="04" label="Unemployment" value={pct(state.economy?.unemployment)} hint={`CPI ${fmt(state.economy?.cpi, 3)}`} accent="amber" />
            <MetricCard index="05" label="Approval" value={pct(state.government?.approval)} hint={`Unrest ${pct(state.government?.unrest)}`} accent="magenta" />
            <MetricCard index="06" label="Districts" value={fmt(state.city?.districts, 0)} hint={`${fmt(state.city?.power_output_mw, 1)} MW generated`} accent="green" />
          </section>

          <section className="dashboard-grid">
            <article className="dashboard-panel dashboard-panel--wide">
              <PanelHeader eyebrow="WORLD PULSE / LIVE" title="Civilization telemetry" meta={`${state.sim_time} · TICK ${state.tick}`} />
              <div className="signal-grid">
                <div className="signal-chart" data-accent="cyan">
                  <div><span>POWER OUTPUT</span><strong>{fmt(state.city?.power_output_mw, 1)} MW</strong></div>
                  <Spark points={series("power_output_mw")} colour="var(--hydra-cyan)" />
                </div>
                <div className="signal-chart" data-accent="amber">
                  <div><span>CONSUMER PRICE INDEX</span><strong>{fmt(state.economy?.cpi, 3)}</strong></div>
                  <Spark points={series("cpi")} colour="var(--hydra-amber)" />
                </div>
                <div className="signal-chart" data-accent="magenta">
                  <div><span>GOVERNMENT TRUST</span><strong>{pct(state.government?.approval)}</strong></div>
                  <Spark points={series("gov_approval")} colour="var(--hydra-magenta)" />
                </div>
              </div>
              <div className="power-readout">
                <div className="power-copy">
                  <span>GRID LOAD</span>
                  <strong>{powerShare.toFixed(1)}%</strong>
                  <small>{fmt(powerDemand, 1)} MW demand of {fmt(powerCapacity, 1)} MW capacity</small>
                </div>
                <div className="power-rail"><i style={{ width: `${powerShare}%` }} /></div>
              </div>
            </article>

            <article className="dashboard-panel">
              <PanelHeader eyebrow="PROOF / STATE" title="System integrity" meta="VERIFIED AT SOURCE" />
              <div className="integrity-score">
                <span className="integrity-ring"><b>100</b><small>STATE</small></span>
                <div>
                  <strong>Deterministic core</strong>
                  <p>Same seed. Same rules. Same world.</p>
                </div>
              </div>
              <dl className="proof-list">
                <div><dt>KERNEL</dt><dd>{state.kernel_version}</dd></div>
                <div><dt>CONFIG HASH</dt><dd>{String(state.config_hash).slice(0, 16)}</dd></div>
                <div><dt>STATE HASH</dt><dd>{String(state.state_hash).slice(0, 16)}</dd></div>
                <div><dt>TIMELINE</dt><dd>{state.timeline_id}</dd></div>
              </dl>
            </article>

            <article className="dashboard-panel">
              <PanelHeader eyebrow="LIFE / NOW" title="Agent activity" meta={`${pct(observedShare)} FULL FIDELITY`} />
              {activity.length ? (
                <div className="activity-list">
                  {activity.map(([label, value], index) => (
                    <div key={label}>
                      <span><i>{String(index + 1).padStart(2, "0")}</i>{label.replace(/_/g, " ")}</span>
                      <strong>{fmt(Number(value), 0)}</strong>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="quiet-state">
                  <span className="quiet-wave" aria-hidden="true" />
                  <strong>THE WORLD IS WAITING</strong>
                  <small>Run the clock to watch routines, work and decisions emerge.</small>
                </div>
              )}
            </article>

            <article className="dashboard-panel dashboard-panel--ledger">
              <PanelHeader eyebrow="EVENTS / IMMUTABLE" title="Consequence ledger" meta={`${events.length} RECENT SIGNALS`} />
              {events.length ? (
                <div className="ledger-list">
                  {events.map((event) => (
                    <Link href={`/causal?event=${event.event_id}`} key={event.event_id}>
                      <span>{event.sim_time}</span>
                      <strong>{String(event.action).replace(/_/g, " ")}</strong>
                      <small>{event.topic} · {pct(event.importance, 0)}</small>
                      <b aria-hidden="true">↗</b>
                    </Link>
                  ))}
                </div>
              ) : (
                <div className="quiet-state quiet-state--ledger">
                  <strong>LEDGER ARMED</strong>
                  <small>The first material consequence will appear when the timeline advances.</small>
                </div>
              )}
            </article>
          </section>
        </>
      )}

      <section className="module-section">
        <div className="section-intro section-intro--modules">
          <span>OBSERVATORY GATES / 02</span>
          <h2>One world. Multiple instruments.</h2>
          <p>Every view reads the same state. Change the lens, never the truth.</p>
        </div>
        <div className="module-grid">
          {MODULES.map((module) => <ModuleLink module={module} key={module.href} />)}
        </div>
      </section>

      <footer className="command-footer">
        <span>OSA TECH GPT × HYDRA WORLD</span>
        <strong>BUILT FOR WORLDS THAT REMEMBER.</strong>
        <span>OBSERVATORY / V0.1</span>
      </footer>
    </div>
  );
}
