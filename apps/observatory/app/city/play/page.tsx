"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import WorldPicker from "@/components/WorldPicker";
import HydraPlayScene, { type PlayTelemetry } from "@/components/world3d/HydraPlayScene";
import { useSelection } from "@/lib/api";
import type { CityModel } from "@/lib/city/state";
import { useCityProjection, useCityStream } from "@/lib/city/useCity";
import { buildPlayLayout, type PlayLayout, type PlayTarget } from "@/lib/world3d/adapter";
import { attachPlayInput, playInput } from "@/lib/world3d/input";

import "./play.css";

const EMPTY_TELEMETRY: PlayTelemetry = { x: 0, z: 0, speed: 0, nearTarget: null };

export default function CityPlayPage() {
  const { worldId, timelineId, select } = useSelection();
  const { model, error } = useCityProjection(timelineId);
  const { live, pulse } = useCityStream(timelineId, model);
  const layout = useMemo(() => (model ? buildPlayLayout(model) : null), [model]);
  const [objectiveIndex, setObjectiveIndex] = useState(0);
  const [telemetry, setTelemetry] = useState<PlayTelemetry>(EMPTY_TELEMETRY);
  const [quality, setQuality] = useState<"low" | "high">("high");
  const [viewMode, setViewMode] = useState<"overview" | "follow">("overview");
  const [toast, setToast] = useState("WAKE THE CITY // podejdź do celu i naciśnij E");
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => attachPlayInput(), []);
  useEffect(() => {
    setObjectiveIndex(0);
    setTelemetry(EMPTY_TELEMETRY);
  }, [timelineId, model?.wire.projection_hash]);

  const flash = useCallback((text: string) => {
    setToast(text);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 3600);
  }, []);

  const advance = useCallback((target: PlayTarget) => {
    setObjectiveIndex((index) => index + 1);
    const messages: Record<string, string> = {
      terminal: "TERMINAL ONLINE // kanał misji otwarty",
      contact: "KONTAKT POTWIERDZONY // agent zsynchronizowany",
      relay: "PRZEKAŹNIK ONLINE // MIASTO BUDZI SIĘ"
    };
    flash(messages[target.kind] ?? "CEL ZAKOŃCZONY");
  }, [flash]);

  const completed = Boolean(layout && objectiveIndex >= layout.targets.length);
  const current = layout?.targets[objectiveIndex] ?? null;

  return (
    <div className="play-shell">
      <header className="play-topbar">
        <div>
          <div className="play-kicker">HYDRA WORLD // LIVE GAME VIEW</div>
          <h2>SEKTOR: {model?.wire.city_id ?? "—"}</h2>
          {model && (
            <div className="play-city-scale">
              {model.wire.districts.length} DISTRICTS · {model.buildings.length} BUILDINGS · {model.segmentCount} STREETS
            </div>
          )}
        </div>
        <div className="play-world-picker"><WorldPicker worldId={worldId} timelineId={timelineId} onSelect={select} /></div>
        <div className="play-actions">
          <button
            className={viewMode === "overview" ? "active" : ""}
            onClick={() => setViewMode((value) => value === "overview" ? "follow" : "overview")}
          >
            {viewMode === "overview" ? "CITY OVERVIEW" : "FOLLOW OSA"}
          </button>
          <button className={quality === "high" ? "active" : ""} onClick={() => setQuality((value) => value === "high" ? "low" : "high")}>QUALITY {quality}</button>
          <Link className="play-back" href="/city">ANALYTIC CITY VIEW</Link>
        </div>
      </header>

      <div className="play-stage">
        {error && <div className="play-blocker">CITY PROJECTION ERROR // {error}</div>}
        {!model && !error && <div className="play-blocker">PROJECTING HYDRA…</div>}
        {model && layout && (
          <HydraPlayScene
            model={model}
            live={live}
            simTime={pulse.simTime}
            layout={layout}
            objectiveIndex={objectiveIndex}
            onAdvance={advance}
            onTelemetry={setTelemetry}
            quality={quality}
            viewMode={viewMode}
          />
        )}

        <section className="play-hud play-hud-left">
          <div className="hud-title">MISSION 001 // WAKE THE CITY</div>
          <div className="hud-objective">{completed ? "✓ CITY NETWORK ONLINE" : current?.label ?? "WAITING FOR PROJECTION"}</div>
          <div className="hud-row"><span>STREAM</span><b className={pulse.connected ? "ok" : "warn"}>{pulse.connected ? "LIVE" : "RECONNECTING"}</b></div>
          <div className="hud-row"><span>SIM TIME</span><b>{pulse.simTime || "—"}</b></div>
          <div className="hud-row"><span>AGENTS</span><b>{pulse.individuals.toLocaleString()}</b></div>
          <div className="hud-row"><span>OBSERVED / DERIVED</span><b>{pulse.presence.observed.toLocaleString()} / {pulse.presence.derived.toLocaleString()}</b></div>
        </section>

        <section className="play-hud play-hud-right">
          <div className="hud-title">AGENT OSA</div>
          <div className="hud-row"><span>X</span><b>{telemetry.x.toFixed(1)}</b></div>
          <div className="hud-row"><span>Z</span><b>{telemetry.z.toFixed(1)}</b></div>
          <div className="hud-row"><span>SPEED</span><b>{telemetry.speed.toFixed(1)} m/s</b></div>
          <div className="hud-controls">WASD / ARROWS · SHIFT SPRINT · E INTERACT</div>
        </section>

        {model && layout && <MiniMap model={model} layout={layout} telemetry={telemetry} />}
        {model && viewMode === "overview" && <DistrictLegend model={model} />}
        <div className="play-graffiti" aria-hidden>OSA // HYDRA</div>
        <div className={telemetry.nearTarget ? "play-interact visible" : "play-interact"}>E // INTERACT</div>
        {toast && <div className="play-toast">{toast}</div>}

        <MobileControls />
      </div>
    </div>
  );
}

function MiniMap({ model, layout, telemetry }: { model: CityModel; layout: PlayLayout; telemetry: PlayTelemetry }) {
  const bounds = model.wire.bounds;
  const width = Math.max(1, bounds.max_x - bounds.min_x);
  const depth = Math.max(1, bounds.max_y - bounds.min_y);
  const px = (x: number) => ((x - bounds.min_x) / width) * 100;
  const py = (z: number) => ((z - bounds.min_y) / depth) * 100;
  return (
    <div className="play-minimap">
      <div className="minimap-title">LIVE MAP</div>
      <svg viewBox="0 0 100 100" role="img" aria-label="Hydra live minimap">
        <rect x="1" y="1" width="98" height="98" rx="3" className="minimap-bound" />
        {model.wire.districts.map((district, index) => {
          const points: string[] = [];
          for (let i = 0; i < district.polygon.length; i += 2) {
            points.push(`${px(district.polygon[i])},${py(district.polygon[i + 1])}`);
          }
          return <polygon key={district.id} points={points.join(" ")} className={`minimap-district district-${index % 8}`} />;
        })}
        {Array.from({ length: model.segmentCount }, (_, index) => index)
          .filter((index) => model.streetKlass[index] === 0)
          .map((index) => {
            const offset = index * 4;
            return (
              <line
                key={`street:${index}`}
                x1={px(model.streetLines[offset])}
                y1={py(model.streetLines[offset + 1])}
                x2={px(model.streetLines[offset + 2])}
                y2={py(model.streetLines[offset + 3])}
                className="minimap-road"
              />
            );
          })}
        {layout.targets.map((target) => (
          <circle key={target.id} cx={px(target.x)} cy={py(target.z)} r="2.2" fill={target.color} opacity="0.8" />
        ))}
        <circle cx={px(telemetry.x)} cy={py(telemetry.z)} r="2.8" className="minimap-player" />
      </svg>
    </div>
  );
}

function DistrictLegend({ model }: { model: CityModel }) {
  return (
    <div className="play-districts" aria-label="Hydra districts">
      <div className="minimap-title">HYDRA // 8 DISTRICTS</div>
      <div className="district-grid">
        {model.wire.districts.map((district, index) => (
          <div key={district.id} className="district-item">
            <i className={`district-dot district-${index % 8}`} />
            <span>{district.name}</span>
            <small>{district.kind}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

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
