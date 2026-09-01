"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import Controls from "@/components/Controls";
import { useI18n } from "@/components/I18n";
import WorldPicker from "@/components/WorldPicker";
import { Spark } from "@/components/Widgets";
import { apiGet, fmt, Json, pct, usePolling, useSelection } from "@/lib/api";

type Accent = "cyan" | "violet" | "magenta" | "amber" | "green" | "blue";

const MODULES: { href: string; code: string; titleKey: string; copyKey: string; accent: Accent }[] = [
  { href: "/city", code: "CITY/02", titleKey: "world.module.city.title", copyKey: "world.module.city.copy", accent: "cyan" },
  { href: "/people", code: "LIFE/05", titleKey: "world.module.people.title", copyKey: "world.module.people.copy", accent: "violet" },
  { href: "/economy", code: "ECON/07", titleKey: "world.module.economy.title", copyKey: "world.module.economy.copy", accent: "amber" },
  { href: "/causal", code: "WHY/13", titleKey: "world.module.causal.title", copyKey: "world.module.causal.copy", accent: "magenta" },
  { href: "/events", code: "LOG/12", titleKey: "world.module.events.title", copyKey: "world.module.events.copy", accent: "green" },
  { href: "/hydra", code: "CORE/01", titleKey: "world.module.hydra.title", copyKey: "world.module.hydra.copy", accent: "blue" }
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
  const { t } = useI18n();
  const demand = Number(state?.city?.power_demand_mw ?? 0);
  const capacity = Number(state?.city?.power_capacity_mw ?? 0);
  const reserve = Math.max(0, capacity - demand);

  return (
    <div className="world-core" aria-label={t("a11y.worldCore")}>
      <div className="core-grid" aria-hidden="true" />
      <div className="core-orbit core-orbit--outer" aria-hidden="true"><i /><i /><i /></div>
      <div className="core-orbit core-orbit--inner" aria-hidden="true"><i /><i /></div>
      <div className={running ? "core-node is-live" : "core-node"}>
        <span>{t("world.core.label")}</span>
        <strong>{state ? fmt(reserve, 1) : "—"}</strong>
        <small>{t("world.core.reserve")}</small>
      </div>
      <div className="core-coordinate core-coordinate--top">Y0 / TL-ZERO</div>
      <div className="core-coordinate core-coordinate--bottom">{t("world.core.deterministic")}</div>
    </div>
  );
}

function ModuleLink({ module }: { module: (typeof MODULES)[number] }) {
  const { t } = useI18n();
  return (
    <Link href={module.href} className="module-link" data-accent={module.accent}>
      <span className="module-code">{module.code}</span>
      <strong>{t(module.titleKey)}</strong>
      <p>{t(module.copyKey)}</p>
      <span className="module-open">{t("world.module.open")} <b aria-hidden="true">↗</b></span>
    </Link>
  );
}

function SyncState({ worldId, error }: { worldId: string; error: string | null }) {
  const { t } = useI18n();
  if (error) {
    return (
      <div className="dashboard-state dashboard-state--error">
        <span>{t("world.sync.interrupted")}</span>
        <strong>{error}</strong>
        <small>{t("world.sync.reconnect")}</small>
      </div>
    );
  }
  return (
    <div className="dashboard-state">
      <span className="sync-loader" aria-hidden="true" />
      <strong>{worldId ? t("world.sync.state") : t("world.sync.noSelection")}</strong>
      <small>{worldId ? t("world.sync.reading") : t("world.sync.choose")}</small>
    </div>
  );
}

export default function WorldPage() {
  const { t, term } = useI18n();
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
            {t("world.hero.kicker")}
          </div>
          <h1>
            {t("world.hero.line1")}<br />
            <span>{t("world.hero.line2")}</span>
          </h1>
          <p>
            {t("world.hero.copy")}
          </p>
          <div className="hero-actions">
            <Link href="/city" className="action action--primary">{t("world.hero.enterCity")} <span>↗</span></Link>
            <Link href="/causal" className="action">{t("world.hero.trace")} <span>→</span></Link>
          </div>
          <div className="hero-proof">
            <span><b>01</b> {t("world.hero.noMocks")}</span>
            <span><b>02</b> {t("world.hero.sealed")}</span>
            <span><b>03</b> {t("world.hero.proof")}</span>
          </div>
        </div>

        <WorldCore state={state} running={running} />

        <div className="hero-telemetry">
          <div><span>{t("world.telemetry.world")}</span><strong>{state?.city?.name ?? "HYDRA"}</strong></div>
          <div><span>{t("world.telemetry.simTime")}</span><strong>{state?.sim_time ?? t("world.telemetry.syncing")}</strong></div>
          <div><span>{t("world.telemetry.mode")}</span><strong className={running ? "good" : "warn"}>{term(running ? "running" : "paused")}</strong></div>
          <div><span>{t("world.telemetry.state")}</span><strong>{term(state?.phase ?? "—")}</strong></div>
        </div>
      </section>

      <section className="mobile-priority-card mobile-live-city" aria-label={t("world.mobileCity.title")}>
        <div>
          <span>{t("world.mobileCity.eyebrow")}</span>
          <h2>{t("world.mobileCity.title")}</h2>
          <p>{t("world.mobileCity.copy")}</p>
        </div>
        <div className="mobile-city-facts">
          <strong>{state?.city?.name ?? "HYDRA"}</strong>
          <small>{state ? `${fmt(state.population, 0)} · ${state.sim_time}` : t("world.telemetry.syncing")}</small>
        </div>
        <Link href="/city" className="action action--primary">{t("world.mobileCity.open")} <span>↗</span></Link>
      </section>

      <section className="control-deck" aria-label={t("a11y.controlDeck")}>
        <div className="section-intro">
          <span>{t("world.control.eyebrow")}</span>
          <h2>{t("world.control.title")}</h2>
        </div>
        <div className="control-grid">
          <WorldPicker worldId={worldId} timelineId={timelineId} onSelect={select} variant="command" />
          <Controls worldId={worldId} timelineId={timelineId} control={control} onChanged={refreshControl} />
        </div>
      </section>

      <section className="mobile-priority-card mobile-event-summary" aria-label={t("world.mobileEvents.title")}>
        <PanelHeader eyebrow={t("world.mobileEvents.eyebrow")} title={t("world.mobileEvents.title")} />
        {events.length ? (
          <div className="mobile-event-list">
            {events.slice(0, 3).map((event) => (
              <Link href={`/causal?event=${event.event_id}`} key={event.event_id}>
                <span>{event.sim_time}</span>
                <strong>{term(event.action)}</strong>
                <b aria-hidden="true">↗</b>
              </Link>
            ))}
          </div>
        ) : <p>{t("world.mobileEvents.empty")}</p>}
      </section>

      {!state ? (
        <SyncState worldId={worldId} error={stateError} />
      ) : (
        <>
          <section className="metrics-grid" aria-label={t("a11y.worldMetrics")}>
            <MetricCard index="01" label={t("world.metrics.population")} value={fmt(state.population, 0)} hint={t("world.metrics.populationHint", { count: fmt(state.individuals, 0) })} accent="cyan" />
            <MetricCard index="02" label={t("world.metrics.minds")} value={fmt(state.persistent_agents, 0)} hint={t("world.metrics.mindsHint")} accent="violet" />
            <MetricCard index="03" label={t("world.metrics.companies")} value={fmt(state.companies, 0)} hint={t("world.metrics.companiesHint")} accent="blue" />
            <MetricCard index="04" label={t("world.metrics.unemployment")} value={pct(state.economy?.unemployment)} hint={t("world.metrics.cpiHint", { value: fmt(state.economy?.cpi, 3) })} accent="amber" />
            <MetricCard index="05" label={t("world.metrics.approval")} value={pct(state.government?.approval)} hint={t("world.metrics.unrestHint", { value: pct(state.government?.unrest) })} accent="magenta" />
            <MetricCard index="06" label={t("world.metrics.districts")} value={fmt(state.city?.districts, 0)} hint={t("world.metrics.powerHint", { value: fmt(state.city?.power_output_mw, 1) })} accent="green" />
          </section>

          <section className="dashboard-grid">
            <article className="dashboard-panel dashboard-panel--wide">
              <PanelHeader eyebrow={t("world.pulse.eyebrow")} title={t("world.pulse.title")} meta={`${state.sim_time} · TICK ${state.tick}`} />
              <div className="signal-grid">
                <div className="signal-chart" data-accent="cyan">
                  <div><span>{t("world.pulse.power")}</span><strong>{fmt(state.city?.power_output_mw, 1)} MW</strong></div>
                  <Spark points={series("power_output_mw")} colour="var(--hydra-cyan)" />
                </div>
                <div className="signal-chart" data-accent="amber">
                  <div><span>{t("world.pulse.cpi")}</span><strong>{fmt(state.economy?.cpi, 3)}</strong></div>
                  <Spark points={series("cpi")} colour="var(--hydra-amber)" />
                </div>
                <div className="signal-chart" data-accent="magenta">
                  <div><span>{t("world.pulse.trust")}</span><strong>{pct(state.government?.approval)}</strong></div>
                  <Spark points={series("gov_approval")} colour="var(--hydra-magenta)" />
                </div>
              </div>
              <div className="power-readout">
                <div className="power-copy">
                  <span>{t("world.pulse.gridLoad")}</span>
                  <strong>{powerShare.toFixed(1)}%</strong>
                  <small>{t("world.pulse.demand", { demand: fmt(powerDemand, 1), capacity: fmt(powerCapacity, 1) })}</small>
                </div>
                <div className="power-rail"><i style={{ width: `${powerShare}%` }} /></div>
              </div>
            </article>

            <article className="dashboard-panel">
              <PanelHeader eyebrow={t("world.integrity.eyebrow")} title={t("world.integrity.title")} meta={t("world.integrity.source")} />
              <div className="integrity-score">
                <span className="integrity-ring"><b>100</b><small>{t("common.state")}</small></span>
                <div>
                  <strong>{t("world.integrity.deterministic")}</strong>
                  <p>{t("world.integrity.copy")}</p>
                </div>
              </div>
              <dl className="proof-list">
                <div><dt>{t("world.integrity.kernel")}</dt><dd>{state.kernel_version}</dd></div>
                <div><dt>{t("world.integrity.config")}</dt><dd>{String(state.config_hash).slice(0, 16)}</dd></div>
                <div><dt>{t("world.integrity.state")}</dt><dd>{String(state.state_hash).slice(0, 16)}</dd></div>
                <div><dt>{t("world.integrity.timeline")}</dt><dd>{state.timeline_id}</dd></div>
              </dl>
            </article>

            <article className="dashboard-panel">
              <PanelHeader eyebrow={t("world.activity.eyebrow")} title={t("world.activity.title")} meta={t("world.activity.fidelity", { value: pct(observedShare) })} />
              {activity.length ? (
                <div className="activity-list">
                  {activity.map(([label, value], index) => (
                    <div key={label}>
                      <span><i>{String(index + 1).padStart(2, "0")}</i>{term(label)}</span>
                      <strong>{fmt(Number(value), 0)}</strong>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="quiet-state">
                  <span className="quiet-wave" aria-hidden="true" />
                  <strong>{t("world.activity.waiting")}</strong>
                  <small>{t("world.activity.copy")}</small>
                </div>
              )}
            </article>

            <article className="dashboard-panel dashboard-panel--ledger">
              <PanelHeader eyebrow={t("world.ledger.eyebrow")} title={t("world.ledger.title")} meta={t("world.ledger.recent", { count: events.length })} />
              {events.length ? (
                <div className="ledger-list">
                  {events.map((event) => (
                    <Link href={`/causal?event=${event.event_id}`} key={event.event_id}>
                      <span>{event.sim_time}</span>
                      <strong>{term(event.action)}</strong>
                      <small>{term(event.topic)} · {pct(event.importance, 0)}</small>
                      <b aria-hidden="true">↗</b>
                    </Link>
                  ))}
                </div>
              ) : (
                <div className="quiet-state quiet-state--ledger">
                  <strong>{t("world.ledger.armed")}</strong>
                  <small>{t("world.ledger.copy")}</small>
                </div>
              )}
            </article>
          </section>
        </>
      )}

      <section className="module-section">
        <div className="section-intro section-intro--modules">
          <span>{t("world.modules.eyebrow")}</span>
          <h2>{t("world.modules.title")}</h2>
          <p>{t("world.modules.copy")}</p>
        </div>
        <div className="module-grid">
          {MODULES.map((module) => <ModuleLink module={module} key={module.href} />)}
        </div>
      </section>

      <footer className="command-footer">
        <span>OSA TECH GPT × HYDRA WORLD</span>
        <strong>{t("world.footer")}</strong>
        <span>OBSERVATORY / V0.1</span>
      </footer>
    </div>
  );
}
