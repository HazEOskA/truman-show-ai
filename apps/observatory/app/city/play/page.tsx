"use client";

/**
 * MISSION 01 — WAKE THE CITY.
 *
 * The jury's way in.
 *
 * Every other page in the Observatory answers a question you already know how to ask. This
 * one is for the five minutes in which somebody who has never seen Hydra has to understand
 * what it claims and why the claim is credible. So it is a mission, with a route, and each
 * stop on the route opens the evidence for one architectural claim — read live out of the
 * running simulation, never out of this file.
 *
 * Three rules held this screen together:
 *
 * 1. **The dossier never states a number of its own.** Every figure in it is resolved from
 *    the world state, the frame stream or the projection, and a figure this page cannot read
 *    is shown as a dash rather than as a plausible-looking substitute.
 * 2. **A jury should not have to play.** Autopilot is on by default: the agent walks its own
 *    route and stops to read. Keys take over the instant anyone touches them.
 * 3. **The city stays visible.** Panels are narrow and translucent, and the camera pulls in
 *    rather than cutting away, because the argument is about the city behind the panel.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import WorldPicker from "@/components/WorldPicker";
import HydraPlayScene, { type PlayTelemetry } from "@/components/world3d/HydraPlayScene";
import { fmt, Json, pct, usePolling, useSelection } from "@/lib/api";
import type { CityModel } from "@/lib/city/state";
import { useCityProjection, useCityStream, type CityPulse } from "@/lib/city/useCity";
import { buildPlayLayout, type PlayLayout, type PlayTarget } from "@/lib/world3d/adapter";
import { MISSION, STATIONS, type EvidenceKey, type Station } from "@/lib/world3d/mission";
import { attachPlayInput, playInput } from "@/lib/world3d/input";

import "./play.css";

const EMPTY_TELEMETRY: PlayTelemetry = { x: 0, z: 0, speed: 0, distance: 0, nearTarget: null };

type Screen = "briefing" | "field" | "dossier" | "debrief";

export default function CityPlayPage() {
  const { worldId, timelineId, select } = useSelection();
  const { model, error } = useCityProjection(timelineId);
  const { live, pulse } = useCityStream(timelineId, model);
  const layout = useMemo(() => (model ? buildPlayLayout(model) : null), [model]);

  // The dossier reads identity and metrics, which move slowly, and the live HUD is fed by
  // the frame stream rather than by polling. `/state` walks fifty thousand residents to
  // answer -- it costs the API seconds, not milliseconds -- so asking for it often is how a
  // single open tab starves every other reader, this page's own stream included.
  const base = worldId ? `/worlds/${worldId}/timelines/${timelineId}` : null;
  const { data: state } = usePolling<Json>(base ? `${base}/state` : null, 15000);
  const { data: snapshots } = usePolling<Json>(base ? `${base}/snapshots` : null, 60000);

  const [screen, setScreen] = useState<Screen>("briefing");
  const [logged, setLogged] = useState(0);
  const [openStation, setOpenStation] = useState<Station | null>(null);
  const [telemetry, setTelemetry] = useState<PlayTelemetry>(EMPTY_TELEMETRY);
  const [quality, setQuality] = useState<"low" | "high">("high");
  const [autopilot, setAutopilot] = useState(true);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => attachPlayInput(), []);

  // A new world is a new mission: nothing carries over from the last one.
  useEffect(() => {
    setScreen("briefing");
    setLogged(0);
    setOpenStation(null);
    setTelemetry(EMPTY_TELEMETRY);
  }, [timelineId, model?.wire.projection_hash]);

  const flash = useCallback((text: string) => {
    setToast(text);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 4200);
  }, []);

  useEffect(() => () => { if (toastTimer.current) clearTimeout(toastTimer.current); }, []);

  const arrive = useCallback(
    (target: PlayTarget) => {
      setOpenStation(target.station);
      setScreen("dossier");
    },
    []
  );

  const confirm = useCallback(() => {
    const next = logged + 1;
    setLogged(next);
    setOpenStation(null);
    if (layout && next >= layout.targets.length) {
      setScreen("debrief");
    } else {
      setScreen("field");
      const upcoming = layout?.targets[next];
      if (upcoming) flash(`EVIDENCE LOGGED // next station ${upcoming.station.code} — ${upcoming.station.title}`);
    }
  }, [logged, layout, flash]);

  // Enter and Space close a dossier, because a jury reaching for "next" reaches for those.
  useEffect(() => {
    if (screen !== "dossier") return;
    const onKey = (event: KeyboardEvent) => {
      if (event.code === "Enter" || event.code === "Space" || event.code === "NumpadEnter") {
        event.preventDefault();
        confirm();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [screen, confirm]);

  const context: EvidenceContext = { state, pulse, model, snapshots };
  const current = layout?.targets[logged] ?? null;
  const running = screen === "field" || screen === "dossier";

  return (
    <div className="play-shell">
      <header className="play-topbar">
        <div className="play-identity">
          <div className="play-kicker">HYDRA WORLD · OBSERVATION LAB</div>
          <h2>{MISSION.code} <span>{MISSION.name}</span></h2>
        </div>

        <ol className="play-progress" aria-label="Mission progress">
          {STATIONS.map((station, index) => (
            <li
              key={station.id}
              className={index < logged ? "done" : index === logged ? "active" : ""}
              style={{ "--station": station.colour } as React.CSSProperties}
              title={`${station.code} — ${station.title}`}
            >
              <b>{station.code}</b>
            </li>
          ))}
        </ol>

        <div className="play-actions">
          <button className={autopilot ? "active" : ""} onClick={() => setAutopilot((value) => !value)}>
            AUTOPILOT {autopilot ? "ON" : "OFF"}
          </button>
          <button onClick={() => setQuality((value) => (value === "high" ? "low" : "high"))}>
            QUALITY {quality}
          </button>
          <Link className="play-back" href="/lab">← LAB</Link>
        </div>
      </header>

      <div className="play-stage">
        {error && <div className="play-blocker">CITY PROJECTION ERROR // {error}</div>}
        {!model && !error && <div className="play-blocker"><span className="play-spinner" />PROJECTING HYDRA…</div>}

        {model && layout && (
          <HydraPlayScene
            model={model}
            live={live}
            simTime={pulse.simTime}
            layout={layout}
            objectiveIndex={logged}
            paused={screen !== "field"}
            autopilot={autopilot && screen === "field"}
            onAdvance={arrive}
            onTelemetry={setTelemetry}
            quality={quality}
          />
        )}

        {running && (
          <>
            <section className="play-hud play-hud-left">
              <div className="hud-title">MISSION LOG</div>
              <ol className="hud-stations">
                {STATIONS.map((station, index) => (
                  <li key={station.id} className={index < logged ? "done" : index === logged ? "active" : ""}>
                    <span className="hud-code" style={{ color: index <= logged ? station.colour : undefined }}>
                      {index < logged ? "✓" : station.code}
                    </span>
                    <span className="hud-station-title">{station.title}</span>
                    <span className="hud-ring">{station.ring}</span>
                  </li>
                ))}
              </ol>
              {current && (
                <div className="hud-heading">
                  <span>TARGET</span>
                  <b>{current.address || current.buildingId}</b>
                  <span>{telemetry.distance > 0 ? `${telemetry.distance.toFixed(0)} m` : "—"}</span>
                </div>
              )}
            </section>

            <section className="play-hud play-hud-right">
              <div className="hud-title">LIVE WORLD</div>
              <div className="hud-row"><span>STREAM</span><b className={pulse.connected ? "ok" : "warn"}>{pulse.connected ? "LIVE" : "RECONNECTING"}</b></div>
              <div className="hud-row"><span>SIM TIME</span><b>{pulse.simTime || "—"}</b></div>
              <div className="hud-row"><span>TICK</span><b>{pulse.tick >= 0 ? pulse.tick.toLocaleString() : "—"}</b></div>
              <div className="hud-row"><span>INDIVIDUALS</span><b>{pulse.individuals.toLocaleString()}</b></div>
              <div className="hud-row"><span>OBSERVED / DERIVED</span><b>{pulse.presence.observed.toLocaleString()} / {pulse.presence.derived.toLocaleString()}</b></div>
              <div className="hud-row"><span>COHORTS</span><b>{pulse.cohortPopulation.toLocaleString()}</b></div>
              <div className="hud-divider" />
              <div className="hud-row"><span>OSA X / Z</span><b>{telemetry.x.toFixed(0)} / {telemetry.z.toFixed(0)}</b></div>
              <div className="hud-row"><span>SPEED</span><b>{telemetry.speed.toFixed(1)} m/s</b></div>
              <div className="hud-controls">
                {autopilot ? "AUTOPILOT GUIDING · WASD TAKES CONTROL" : "WASD / ARROWS · SHIFT SPRINT · E INTERACT"}
              </div>
            </section>

            {model && layout && <MiniMap model={model} layout={layout} logged={logged} telemetry={telemetry} />}
            <div className={telemetry.nearTarget && screen === "field" ? "play-interact visible" : "play-interact"}>E // CONNECT</div>
            {toast && <div className="play-toast">{toast}</div>}
            <MobileControls />
          </>
        )}

        {screen === "briefing" && (
          <Briefing
            layout={layout}
            ready={Boolean(model && layout)}
            worldId={worldId}
            timelineId={timelineId}
            onSelect={select}
            onStart={() => {
              setScreen("field");
              flash(`START // station ${STATIONS[0].code} — ${STATIONS[0].title}`);
            }}
          />
        )}

        {screen === "dossier" && openStation && (
          <Dossier
            station={openStation}
            index={logged}
            total={layout?.targets.length ?? STATIONS.length}
            context={context}
            onConfirm={confirm}
          />
        )}

        {screen === "debrief" && (
          <Debrief
            context={context}
            onReplay={() => {
              setLogged(0);
              setScreen("briefing");
            }}
          />
        )}
      </div>
    </div>
  );
}

// -- briefing ----------------------------------------------------------------------------

function Briefing({
  layout,
  ready,
  worldId,
  timelineId,
  onSelect,
  onStart
}: {
  layout: PlayLayout | null;
  ready: boolean;
  worldId: string;
  timelineId: string;
  onSelect: (world: string, timeline: string) => void;
  onStart: () => void;
}) {
  return (
    <div className="play-overlay">
      <div className="play-sheet briefing">
        <div className="sheet-kicker">{MISSION.code} · BRIEFING</div>
        <h1>{MISSION.name}</h1>
        <div className="sheet-meta">
          <span>OPERATOR <b>{MISSION.operator}</b></span>
          <span>STATIONS <b>{layout?.targets.length ?? STATIONS.length}</b></span>
          <span>ROUTE <b>{layout ? `${Math.round(layout.routeMetres)} m` : "—"}</b></span>
          <span>TIMELINE <b>{timelineId}</b></span>
        </div>

        {MISSION.prologue.map((paragraph) => (
          <p key={paragraph.slice(0, 24)}>{paragraph}</p>
        ))}

        <div className="sheet-stations">
          {STATIONS.map((station) => (
            <div key={station.id} className="sheet-station" style={{ "--station": station.colour } as React.CSSProperties}>
              <b>{station.code}</b>
              <span>{station.title}</span>
              <small>{station.ring}</small>
            </div>
          ))}
        </div>

        {!worldId && (
          <div className="sheet-picker">
            <p className="sheet-warn">No world is selected. Choose an existing world or run Genesis — this mission reads a live simulation, never a recording.</p>
            <WorldPicker worldId={worldId} timelineId={timelineId} onSelect={onSelect} />
          </div>
        )}

        <div className="sheet-actions">
          <button className="sheet-go" disabled={!ready} onClick={onStart}>
            {ready ? "BEGIN MISSION" : "WAITING FOR PROJECTION…"}
          </button>
          <Link className="sheet-link" href="/lab">Return to Laboratory</Link>
        </div>
        <p className="sheet-foot">
          Autopilot is enabled and will follow the route. Use WASD at any time to take control.
        </p>
      </div>
    </div>
  );
}

// -- dossier -----------------------------------------------------------------------------

function Dossier({
  station,
  index,
  total,
  context,
  onConfirm
}: {
  station: Station;
  index: number;
  total: number;
  context: EvidenceContext;
  onConfirm: () => void;
}) {
  return (
    <div className="play-overlay dossier-overlay">
      <div className="play-sheet dossier" style={{ "--station": station.colour } as React.CSSProperties}>
        <div className="sheet-kicker">
          STATION {index + 1}/{total} · {station.ring}
        </div>
        <h1>
          <span className="dossier-code">{station.code}</span> {station.title}
        </h1>

        <p className="dossier-brief">{station.brief}</p>

        <div className="dossier-block">
          <h4>CLAIM</h4>
          <p>{station.thesis}</p>
        </div>
        <div className="dossier-block">
          <h4>HOW IT IS ENFORCED</h4>
          <p>{station.proof}</p>
        </div>
        <div className="dossier-block">
          <h4>WHAT WOULD FALSIFY IT</h4>
          <p>{station.falsifier}</p>
        </div>

        <div className="dossier-block">
          <h4>EVIDENCE FROM THE LIVE WORLD</h4>
          <div className="dossier-evidence">
            {station.evidence.map((item) => (
              <div key={item.key} className="evidence">
                <span>{item.label}</span>
                <b>{resolveEvidence(item.key, context)}</b>
              </div>
            ))}
          </div>
        </div>

        <div className="dossier-foot">
          <span className="dossier-test">TEST · {station.test}</span>
          <Link href={station.href} className="dossier-link">{station.hrefLabel} →</Link>
        </div>

        <button className="sheet-go" onClick={onConfirm}>
          {index + 1 >= total ? "CLOSE AUDIT" : "LOG EVIDENCE & CONTINUE"}
        </button>
      </div>
    </div>
  );
}

// -- debrief -----------------------------------------------------------------------------

function Debrief({ context, onReplay }: { context: EvidenceContext; onReplay: () => void }) {
  return (
    <div className="play-overlay">
      <div className="play-sheet debrief">
        <div className="sheet-kicker">{MISSION.code} · {MISSION.epilogueTitle}</div>
        <h1>AUDIT COMPLETE</h1>
        {MISSION.epilogue.map((paragraph) => (
          <p key={paragraph.slice(0, 24)}>{paragraph}</p>
        ))}

        <div className="debrief-grid">
          {STATIONS.map((station) => (
            <div key={station.id} className="debrief-card" style={{ "--station": station.colour } as React.CSSProperties}>
              <div className="debrief-head">
                <b>{station.code}</b>
                <span>{station.title}</span>
              </div>
              <div className="debrief-ring">{station.ring}</div>
              <p>{station.thesis}</p>
              <div className="debrief-evidence">
                {station.evidence.slice(0, 3).map((item) => (
                  <span key={item.key}>
                    {item.label} <b>{resolveEvidence(item.key, context)}</b>
                  </span>
                ))}
              </div>
              <small>{station.test}</small>
            </div>
          ))}
        </div>

        <div className="debrief-equation">
          <code>STATE(t) + AGENT_DECISIONS(t) + WORLD_RULES + DETERMINISTIC_RANDOMNESS = STATE(t+1)</code>
          <span>
            A language model is never part of this equation. It is an optional layer that may
            propose an action or write a sentence; the full simulation completes without a
            configured provider, and the determinism tests require that property.
          </span>
        </div>

        <div className="sheet-actions">
          <button className="sheet-go" onClick={onReplay}>REPLAY MISSION</button>
          <Link className="sheet-link" href="/lab">Laboratory</Link>
          <Link className="sheet-link" href="/city">City View</Link>
          <Link className="sheet-link" href="/causal">Causal graph</Link>
        </div>
      </div>
    </div>
  );
}

// -- evidence ----------------------------------------------------------------------------

interface EvidenceContext {
  state: Json | null;
  pulse: CityPulse;
  model: CityModel | null;
  snapshots: Json | null;
}

/**
 * Every number the dossier shows, resolved from the running world.
 *
 * There is no fallback table of plausible-looking values on purpose: a figure this view
 * cannot read is shown as a dash. A demo that quietly substitutes a nice number for a
 * missing one is exactly the thing this mission is arguing Hydra does not do.
 */
function resolveEvidence(key: EvidenceKey, { state, pulse, model, snapshots }: EvidenceContext): string {
  const metrics = (state?.metrics ?? {}) as Json;
  const economy = (state?.economy ?? {}) as Json;
  const short = (value: unknown) => (value ? String(value).slice(0, 12) : "—");
  const count = (value: unknown) =>
    value === undefined || value === null ? "—" : Number(value).toLocaleString();

  switch (key) {
    case "seed": return state ? String(state.seed) : "—";
    case "kernel_version": return state ? String(state.kernel_version) : "—";
    case "config_hash": return short(state?.config_hash);
    case "state_hash": return short(state?.state_hash);
    case "tick": return pulse.tick >= 0 ? pulse.tick.toLocaleString() : count(state?.tick);
    case "day": return count(state?.day);
    case "sim_time": return pulse.simTime || String(state?.sim_time ?? "—");
    case "phase": return state ? String(state.phase) : "—";
    case "timeline_id": return String(state?.timeline_id ?? "—");
    case "actions_executed": return count(metrics.actions_executed_total);
    case "districts": return model ? String(model.wire.districts.length) : "—";
    case "buildings": return model ? model.buildings.length.toLocaleString() : "—";
    case "streets": return model ? model.segmentCount.toLocaleString() : "—";
    case "projection_hash": return short(model?.wire.projection_hash);
    case "population": return count(state?.population);
    case "individuals": return pulse.individuals ? pulse.individuals.toLocaleString() : count(state?.individuals);
    case "persistent_agents": return count(state?.persistent_agents);
    case "active_agents": return count(metrics.active_agents);
    case "sleeping_agents": return count(metrics.sleeping_agents);
    case "agent_ticks": return count(metrics.agent_ticks);
    case "tokens_used": return count(metrics.tokens_used);
    case "cohort_population": return pulse.cohortPopulation
      ? pulse.cohortPopulation.toLocaleString()
      : count(state?.population !== undefined && state?.individuals !== undefined
          ? Number(state.population) - Number(state.individuals)
          : undefined);
    case "companies": return count(state?.companies);
    case "unemployment": return economy.unemployment === undefined ? "—" : pct(Number(economy.unemployment));
    case "cpi": return economy.cpi === undefined ? "—" : fmt(Number(economy.cpi), 3);
    case "energy_price": return economy.energy_price === undefined ? "—" : `${fmt(Number(economy.energy_price), 0)} minor/kWh`;
    // Money is carried in integer minor units everywhere in Hydra; this is the one place it
    // is turned into HYD, for reading, and never for arithmetic.
    case "wages_paid": return metrics.wages_paid_minor === undefined
      ? "—"
      : `${fmt(Number(metrics.wages_paid_minor) / 100, 0)} HYD`;
    case "production_units": return count(metrics.production_units);
    case "observed": return pulse.presence.observed.toLocaleString();
    case "derived": return pulse.presence.derived.toLocaleString();
    case "observed_share": return pct(pulse.presence.observed_share);
    case "publications": return count(metrics.publications);
    case "facts_known": return count(metrics.facts_known);
    case "info_deliveries": return count(metrics.info_deliveries);
    case "snapshots": {
      const list = snapshots?.snapshots;
      return Array.isArray(list) ? String(list.length) : "—";
    }
    default: return "—";
  }
}

// -- minimap -----------------------------------------------------------------------------

function MiniMap({
  model,
  layout,
  logged,
  telemetry
}: {
  model: CityModel;
  layout: PlayLayout;
  logged: number;
  telemetry: PlayTelemetry;
}) {
  // Framed on the route, not on the city. Hydra is eleven kilometres wide and the mission
  // crosses a few hundred metres of it, so a minimap drawn to the city's bounds is six dots
  // on top of each other -- true, and useless for finding the next one.
  const points = [...layout.targets.map((t) => ({ x: t.x, z: t.z })), { x: telemetry.x, z: telemetry.z }];
  const pad = 60;
  const minX = Math.min(...points.map((p) => p.x)) - pad;
  const maxX = Math.max(...points.map((p) => p.x)) + pad;
  const minZ = Math.min(...points.map((p) => p.z)) - pad;
  const maxZ = Math.max(...points.map((p) => p.z)) + pad;
  const size = Math.max(maxX - minX, maxZ - minZ, 1);
  const px = (x: number) => ((x - (minX + maxX) / 2) / size + 0.5) * 100;
  const py = (z: number) => ((z - (minZ + maxZ) / 2) / size + 0.5) * 100;
  const route = layout.targets.map((target) => `${px(target.x)},${py(target.z)}`).join(" ");

  return (
    <div className="play-minimap">
      <div className="minimap-title">ROUTE</div>
      <svg viewBox="0 0 100 100" role="img" aria-label="Mission route">
        <rect x="1" y="1" width="98" height="98" rx="3" className="minimap-bound" />
        <polyline points={route} className="minimap-route" />
        {layout.targets.map((target, index) => (
          <circle
            key={target.id}
            cx={px(target.x)}
            cy={py(target.z)}
            r={index === logged ? 3.2 : 2.1}
            fill={index < logged ? "#3f8f6a" : target.colour}
            opacity={index < logged ? 0.55 : 0.95}
          />
        ))}
        <circle cx={px(telemetry.x)} cy={py(telemetry.z)} r="2.8" className="minimap-player" />
      </svg>
    </div>
  );
}

// -- touch -------------------------------------------------------------------------------

function MobileControls() {
  const pad = useRef<HTMLDivElement>(null);
  const pointer = useRef<number | null>(null);
  const [knob, setKnob] = useState({ x: 0, y: 0 });

  const update = (event: React.PointerEvent<HTMLDivElement>) => {
    const element = pad.current;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    let x = (event.clientX - (rect.left + rect.width / 2)) / (rect.width / 2);
    let y = (event.clientY - (rect.top + rect.height / 2)) / (rect.height / 2);
    const length = Math.hypot(x, y);
    if (length > 1) { x /= length; y /= length; }
    playInput.joyX = x;
    playInput.joyY = y;
    setKnob({ x: x * 34, y: y * 34 });
  };

  const release = () => {
    pointer.current = null;
    playInput.joyX = 0;
    playInput.joyY = 0;
    playInput.sprint = false;
    setKnob({ x: 0, y: 0 });
  };

  return (
    <div className="mobile-controls">
      <div
        ref={pad}
        className="mobile-joy"
        onPointerDown={(event) => { pointer.current = event.pointerId; pad.current?.setPointerCapture(event.pointerId); update(event); }}
        onPointerMove={(event) => { if (pointer.current === event.pointerId) update(event); }}
        onPointerUp={release}
        onPointerCancel={release}
      >
        <div className="mobile-knob" style={{ transform: `translate(${knob.x}px, ${knob.y}px)` }} />
      </div>
      <div className="mobile-buttons">
        <button onPointerDown={() => { playInput.sprint = true; }} onPointerUp={() => { playInput.sprint = false; }} onPointerCancel={() => { playInput.sprint = false; }}>SPR</button>
        <button className="interact" onPointerDown={() => { playInput.interactQueued = true; }}>E</button>
      </div>
    </div>
  );
}
