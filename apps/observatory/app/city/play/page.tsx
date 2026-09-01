"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import WorldPicker from "@/components/WorldPicker";
import { useI18n } from "@/components/I18n";
import HydraPlayScene, { type PlayTelemetry } from "@/components/world3d/HydraPlayScene";
import { useSelection } from "@/lib/api";
import type { CityModel } from "@/lib/city/state";
import { useCityProjection, useCityStream } from "@/lib/city/useCity";
import { buildPlayLayout, type PlayLayout, type PlayTarget } from "@/lib/world3d/adapter";
import { attachPlayInput, playInput } from "@/lib/world3d/input";

import "./play.css";

const EMPTY_TELEMETRY: PlayTelemetry = { x: 0, z: 0, speed: 0, nearTarget: null };

export default function CityPlayPage() {
  const { t, term } = useI18n();
  const { worldId, timelineId, select } = useSelection();
  const { model, error } = useCityProjection(timelineId);
  const { live, pulse } = useCityStream(timelineId, model);
  const layout = useMemo(() => (model ? buildPlayLayout(model) : null), [model]);
  const [objectiveIndex, setObjectiveIndex] = useState(0);
  const [telemetry, setTelemetry] = useState<PlayTelemetry>(EMPTY_TELEMETRY);
  const [quality, setQuality] = useState<"low" | "high">("high");
  const [toast, setToast] = useState("");
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => attachPlayInput(), []);
  useEffect(() => setToast(t("play.wake")), [t]);
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
      terminal: t("play.terminal"),
      contact: t("play.contact"),
      relay: t("play.relay")
    };
    flash(messages[target.kind] ?? t("play.complete"));
  }, [flash, t]);

  const completed = Boolean(layout && objectiveIndex >= layout.targets.length);
  const current = layout?.targets[objectiveIndex] ?? null;

  return (
    <div className="play-shell">
      <header className="play-topbar">
        <div>
          <div className="play-kicker">{t("play.kicker")}</div>
          <h2>{t("play.sector", { id: model?.wire.city_id ?? "—" })}</h2>
        </div>
        <div className="play-world-picker"><WorldPicker worldId={worldId} timelineId={timelineId} onSelect={select} /></div>
        <div className="play-actions">
          <button className={quality === "high" ? "active" : ""} onClick={() => setQuality((value) => value === "high" ? "low" : "high")}>{t("play.quality", { value: term(quality) })}</button>
          <Link className="play-back" href="/city">{t("play.analytics")}</Link>
        </div>
      </header>

      <div className="play-stage">
        {error && <div className="play-blocker">{t("play.projectionError", { error })}</div>}
        {!model && !error && <div className="play-blocker">{t("play.projecting")}</div>}
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
          />
        )}

        <section className="play-hud play-hud-left">
          <div className="hud-title">{t("play.mission")}</div>
          <div className="hud-objective">{completed ? t("play.cityOnline") : current?.label ? t(current.label) : t("play.waiting")}</div>
          <div className="hud-row"><span>{t("play.stream")}</span><b className={pulse.connected ? "ok" : "warn"}>{pulse.connected ? t("nav.live") : t("value.reconnecting")}</b></div>
          <div className="hud-row"><span>{t("play.simTime")}</span><b>{pulse.simTime || "—"}</b></div>
          <div className="hud-row"><span>{t("play.agents")}</span><b>{pulse.individuals.toLocaleString()}</b></div>
          <div className="hud-row"><span>{t("play.observedDerived")}</span><b>{pulse.presence.observed.toLocaleString()} / {pulse.presence.derived.toLocaleString()}</b></div>
        </section>

        <section className="play-hud play-hud-right">
          <div className="hud-title">AGENT OSA</div>
          <div className="hud-row"><span>X</span><b>{telemetry.x.toFixed(1)}</b></div>
          <div className="hud-row"><span>Z</span><b>{telemetry.z.toFixed(1)}</b></div>
          <div className="hud-row"><span>{t("play.speed")}</span><b>{telemetry.speed.toFixed(1)} m/s</b></div>
          <div className="hud-controls">{t("play.controls")}</div>
        </section>

        {model && layout && <MiniMap model={model} layout={layout} telemetry={telemetry} />}
        <div className="play-graffiti" aria-hidden>OSA // HYDRA</div>
        <div className={telemetry.nearTarget ? "play-interact visible" : "play-interact"}>{t("play.interact")}</div>
        {toast && <div className="play-toast">{toast}</div>}

        <MobileControls />
      </div>
    </div>
  );
}

function MiniMap({ model, layout, telemetry }: { model: CityModel; layout: PlayLayout; telemetry: PlayTelemetry }) {
  const { t } = useI18n();
  const bounds = model.wire.bounds;
  const width = Math.max(1, bounds.max_x - bounds.min_x);
  const depth = Math.max(1, bounds.max_y - bounds.min_y);
  const px = (x: number) => ((x - bounds.min_x) / width) * 100;
  const py = (z: number) => ((z - bounds.min_y) / depth) * 100;
  return (
    <div className="play-minimap">
      <div className="minimap-title">{t("play.map")}</div>
      <svg viewBox="0 0 100 100" role="img" aria-label={t("play.minimap")}>
        <rect x="1" y="1" width="98" height="98" rx="3" className="minimap-bound" />
        {layout.targets.map((target) => (
          <circle key={target.id} cx={px(target.x)} cy={py(target.z)} r="2.2" fill={target.color} opacity="0.8" />
        ))}
        <circle cx={px(telemetry.x)} cy={py(telemetry.z)} r="2.8" className="minimap-player" />
      </svg>
    </div>
  );
}

function MobileControls() {
  const { t } = useI18n();
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
        <button onPointerDown={() => { playInput.sprint = true; }} onPointerUp={() => { playInput.sprint = false; }} onPointerCancel={() => { playInput.sprint = false; }}>{t("play.sprintShort")}</button>
        <button className="interact" onPointerDown={() => { playInput.interactQueued = true; }}>E</button>
      </div>
    </div>
  );
}
