"use client";

/**
 * MAP — Hydra from above, in three dimensions.
 *
 * The old Map view drew each district as a soft blob on a canvas. It was honest about the
 * numbers and useless as a map: a blob cannot tell you that the unrest is in the terraces
 * behind the plant, because a blob has no terraces and no plant.
 *
 * So this is the city itself — the same cubes, streets and dots the mission walks through,
 * seen from the air, with the data layer painted onto the ground the buildings stand on.
 * That is the whole idea: a value you can see *and* the place it belongs to, at once.
 *
 * Nothing here re-implements the city. Every mesh comes from `CityLayers`, so a change to
 * how Hydra looks lands in the mission and the map together and they cannot drift.
 */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

import {
  CityBuildings,
  CityCitizens,
  CityGround,
  CityLight,
  CityStreets,
  DistrictLabels,
  DistrictPlates,
  LandUse
} from "@/components/world3d/CityLayers";
import { Header } from "@/components/Page";
import { fmt, Json, usePolling, useSelection } from "@/lib/api";
import { rampColour } from "@/lib/city/palette";
import type { CityModel } from "@/lib/city/state";
import type { LayerMeta } from "@/lib/city/types";
import { useCityProjection, useCityStream } from "@/lib/city/useCity";
import { brighten, ZONE_LEGEND, zoneColour } from "@/lib/world3d/theme";

import "./map.css";

export default function MapPage() {
  const { timelineId } = useSelection();
  const { model, error } = useCityProjection(timelineId);
  const { live, pulse } = useCityStream(timelineId, model);

  // One request returns the catalogue and every layer's values, so switching layers is
  // instant and the district panel can show all of them at once without another round trip.
  const { data: layers } = usePolling<Json>(timelineId ? `/city/${timelineId}/layers` : null, 4000);
  const catalogue: LayerMeta[] = (layers?.catalogue ?? []) as LayerMeta[];
  const values: Record<string, Record<string, number>> = (layers?.values ?? {}) as Record<string, Record<string, number>>;

  const [layerId, setLayerId] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [showPeople, setShowPeople] = useState(true);

  const meta = useMemo(() => catalogue.find((entry) => entry.id === layerId) ?? null, [catalogue, layerId]);
  const districtLayers = catalogue.filter((entry) => entry.scope === "district");
  const buildingLayers = catalogue.filter((entry) => entry.scope === "building");

  const normalise = useCallback(
    (value: number) => {
      if (!meta) return 0;
      const span = meta.high - meta.low || 1;
      return Math.max(0, Math.min(1, (value - meta.low) / span));
    },
    [meta]
  );

  /** District ground colour: the layer when one is on, the district's own kind when not. */
  const paintDistrict = useCallback(
    (districtId: string) => {
      if (!meta || meta.scope !== "district") return null;
      const value = values[meta.id]?.[districtId];
      if (value === undefined) return null;
      // The palette's ramps are tuned for unlit 2D fills; under a light they lose about a
      // third of their brightness, and a legend that no longer matches the ground is worse
      // than no legend.
      return brighten(rampColour(normalise(value), meta.high_is_bad), 0.24);
    },
    [meta, values, normalise]
  );

  /** Building colour: only a building-scope layer overrides zoning. */
  const paintBuilding = useCallback(
    (building: { id: string }) => {
      if (!meta || meta.scope !== "building") return null;
      const value = values[meta.id]?.[building.id];
      if (value === undefined) return null;
      return brighten(rampColour(normalise(value), meta.high_is_bad), 0.24);
    },
    [meta, values, normalise]
  );

  const district = model && selected ? model.wire.districts.find((entry) => entry.id === selected) ?? null : null;

  return (
    <>
      <Header
        title="Map · 3D"
        right={
          model
            ? `${model.wire.districts.length} districts · ${model.buildings.length.toLocaleString()} buildings · ${pulse.simTime || "—"}`
            : ""
        }
      />

      <div className="map3d">
        <div className="map3d-toolbar">
          <div className="map3d-group">
            <span className="map3d-label">ZONING</span>
            <button className={!layerId ? "primary" : ""} onClick={() => setLayerId(null)}>
              Land use
            </button>
          </div>
          <div className="map3d-group">
            <span className="map3d-label">DISTRICT LAYERS</span>
            {districtLayers.map((entry) => (
              <button key={entry.id} className={layerId === entry.id ? "primary" : ""} onClick={() => setLayerId(entry.id)}>
                {entry.label}
              </button>
            ))}
          </div>
          <div className="map3d-group">
            <span className="map3d-label">BUILDING LAYERS</span>
            {buildingLayers.map((entry) => (
              <button key={entry.id} className={layerId === entry.id ? "primary" : ""} onClick={() => setLayerId(entry.id)}>
                {entry.label}
              </button>
            ))}
            <button className={showPeople ? "primary" : ""} onClick={() => setShowPeople((value) => !value)}>
              People {showPeople ? "on" : "off"}
            </button>
          </div>
        </div>

        <div className="map3d-stage">
          {error && <div className="map3d-blocker">CITY PROJECTION ERROR // {error}</div>}
          {!model && !error && <div className="map3d-blocker">projecting Hydra…</div>}

          {model && (
            <Canvas
              className="map3d-canvas"
              orthographic
              camera={{ position: [0, 1, 1], near: 0.1, far: 80000, zoom: 1 }}
              dpr={[1, 1.75]}
              gl={{ antialias: true, powerPreference: "high-performance" }}
              onPointerMissed={() => setSelected(null)}
            >
              <MapScene
                model={model}
                live={live}
                showPeople={showPeople}
                selected={selected}
                onSelect={setSelected}
                paintDistrict={paintDistrict}
                paintBuilding={paintBuilding}
              />
            </Canvas>
          )}

          <div className="map3d-hint">DRAG obróć · SHIFT+DRAG przesuń · SCROLL przybliż</div>

          <div className="map3d-legend">
            <div className="legend-title">{meta ? meta.label.toUpperCase() : "LAND USE"}</div>
            {meta ? (
              <>
                <div className="legend-ramp" data-bad={meta.high_is_bad ? "1" : "0"} />
                <div className="legend-scale">
                  <span>{fmt(meta.low, 2)}</span>
                  <span>{meta.unit}</span>
                  <span>{fmt(meta.high, 2)}</span>
                </div>
                <div className="legend-source">źródło · {meta.source}</div>
              </>
            ) : (
              <div className="legend-zones">
                {ZONE_LEGEND.map(([kind, label]) => (
                  <span key={kind}>
                    <i style={{ background: `#${zoneColour(kind).toString(16).padStart(6, "0")}` }} />
                    {label}
                  </span>
                ))}
              </div>
            )}
            <div className="legend-dots">
              <span><i className="dot awake" />awake</span>
              <span><i className="dot asleep" />asleep</span>
              <span><i className="dot derived" />derived</span>
            </div>
          </div>

          {district && (
            <aside className="map3d-panel">
              <div className="panel-kicker">{district.kind.toUpperCase()}</div>
              <h3>{district.name}</h3>
              <div className="panel-rows">
                {catalogue
                  .filter((entry) => entry.scope === "district")
                  .map((entry) => {
                    const value = values[entry.id]?.[district.id];
                    return (
                      <div key={entry.id} className={layerId === entry.id ? "active" : ""}>
                        <span>{entry.label}</span>
                        <b>{value === undefined ? "—" : fmt(value, 3)}</b>
                      </div>
                    );
                  })}
              </div>
              <button onClick={() => setSelected(null)}>ZAMKNIJ</button>
            </aside>
          )}
        </div>
      </div>
    </>
  );
}

// -- scene -------------------------------------------------------------------------------

function MapScene({
  model,
  live,
  showPeople,
  selected,
  onSelect,
  paintDistrict,
  paintBuilding
}: {
  model: CityModel;
  live: ReturnType<typeof useCityStream>["live"];
  showPeople: boolean;
  selected: string | null;
  onSelect: (id: string | null) => void;
  paintDistrict: (districtId: string, index: number) => number | null;
  paintBuilding: (building: { id: string }, index: number) => number | null;
}) {
  // The Map is lit at a fixed analytic noon, not at the world's hour.
  //
  // Everywhere else the light follows the simulated clock, and it should: a city that goes
  // dark at 03:00 is telling you something true. Here it would lie. A layer legend maps a
  // colour to a value, and if dusk quietly darkens the ground then the same unrest reads as
  // two different numbers depending on when you looked. The clock still drives the sky in
  // the mission and the City View; on this page the light is an instrument setting.
  const hour = 12;
  return (
    <>
      <MapControls model={model} />
      {/* No fog either: the camera sits kilometres back, and a map that dims with distance
          is a map that lies about the far side of the city. */}
      <CityLight model={model} hour={hour} fog={false} />
      <CityGround model={model} />
      <DistrictPlates model={model} paint={paintDistrict} highlight={selected} onPick={(id) => onSelect(id)} />
      <LandUse model={model} />
      <CityStreets model={model} />
      <CityBuildings model={model} live={live} hour={hour} paint={paintBuilding} emissive={false} />
      {showPeople && <CityCitizens model={model} live={live} max={5000} size={2.2} />}
      <DistrictLabels model={model} />
    </>
  );
}

/**
 * Orbit, pan and zoom, in about forty lines.
 *
 * The alternative is another dependency for something this view needs exactly once. The
 * camera is orthographic on purpose: a data map wants two buildings of the same height to
 * look the same height wherever they stand, and perspective takes that away.
 */
function MapControls({ model }: { model: CityModel }) {
  const { camera, gl, size } = useThree();
  const bounds = model.wire.bounds;
  const span = Math.max(bounds.max_x - bounds.min_x, bounds.max_y - bounds.min_y);

  // Frame what is built, not what is bounded.
  //
  // Hydra's bounds run to the edge of the region and most of that is empty ground the
  // generator never developed. Opening on the bounds puts the whole city in the middle
  // third of the screen as a smudge; opening on the buildings puts it on the screen.
  const built = useMemo(() => {
    let minX = Infinity;
    let maxX = -Infinity;
    let minZ = Infinity;
    let maxZ = -Infinity;
    for (const building of model.buildings) {
      if (building.x < minX) minX = building.x;
      if (building.x > maxX) maxX = building.x;
      if (building.y < minZ) minZ = building.y;
      if (building.y > maxZ) maxZ = building.y;
    }
    if (!Number.isFinite(minX)) {
      return { x: (bounds.min_x + bounds.max_x) / 2, z: (bounds.min_y + bounds.max_y) / 2, span };
    }
    return {
      x: (minX + maxX) / 2,
      z: (minZ + maxZ) / 2,
      span: Math.max(maxX - minX, maxZ - minZ, 200)
    };
  }, [model, bounds.min_x, bounds.max_x, bounds.min_y, bounds.max_y, span]);

  const view = useRef({
    azimuth: Math.PI * 0.25,
    pitch: 0.82,
    target: new THREE.Vector3(built.x, 0, built.z),
    zoom: 1
  });

  useEffect(() => {
    view.current.target.set(built.x, 0, built.z);
    view.current.zoom = Math.min(size.width, size.height) / (built.span * 1.2 || 1);
  }, [built, size.width, size.height]);

  useEffect(() => {
    const element = gl.domElement;
    let dragging = false;
    let panning = false;
    let lastX = 0;
    let lastY = 0;

    const down = (event: PointerEvent) => {
      if (event.button !== 0 && event.button !== 1 && event.button !== 2) return;
      dragging = true;
      panning = event.shiftKey || event.button === 1 || event.button === 2;
      lastX = event.clientX;
      lastY = event.clientY;
      element.setPointerCapture(event.pointerId);
    };
    const move = (event: PointerEvent) => {
      if (!dragging) return;
      const dx = event.clientX - lastX;
      const dy = event.clientY - lastY;
      lastX = event.clientX;
      lastY = event.clientY;
      const v = view.current;
      if (panning) {
        // Panning happens in the ground plane, along the direction the camera is facing, so
        // dragging right always moves the city right no matter how far it has been turned.
        const scale = 1 / v.zoom;
        const cos = Math.cos(v.azimuth);
        const sin = Math.sin(v.azimuth);
        v.target.x -= (dx * cos - dy * sin) * scale;
        v.target.z -= (dx * sin + dy * cos) * scale;
      } else {
        v.azimuth -= dx * 0.006;
        v.pitch = Math.max(0.18, Math.min(1.5, v.pitch + dy * 0.005));
      }
    };
    const up = (event: PointerEvent) => {
      dragging = false;
      panning = false;
      if (element.hasPointerCapture(event.pointerId)) element.releasePointerCapture(event.pointerId);
    };
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      const v = view.current;
      v.zoom = Math.max(0.04, Math.min(14, v.zoom * Math.exp(-event.deltaY * 0.0014)));
    };
    const menu = (event: MouseEvent) => event.preventDefault();

    element.addEventListener("pointerdown", down);
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerup", up);
    element.addEventListener("pointercancel", up);
    element.addEventListener("wheel", wheel, { passive: false });
    element.addEventListener("contextmenu", menu);
    return () => {
      element.removeEventListener("pointerdown", down);
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", up);
      element.removeEventListener("pointercancel", up);
      element.removeEventListener("wheel", wheel);
      element.removeEventListener("contextmenu", menu);
    };
  }, [gl]);

  useFrame((_, dt) => {
    const v = view.current;
    const distance = span * 2.2 + 400;  // ortho: only the direction matters, not the length
    const y = Math.sin(v.pitch) * distance;
    const r = Math.cos(v.pitch) * distance;
    const wanted = new THREE.Vector3(
      v.target.x + Math.sin(v.azimuth) * r,
      y,
      v.target.z + Math.cos(v.azimuth) * r
    );
    camera.position.lerp(wanted, 1 - Math.exp(-dt * 12));
    camera.lookAt(v.target);
    if (camera instanceof THREE.OrthographicCamera) {
      camera.zoom += (v.zoom - camera.zoom) * (1 - Math.exp(-dt * 12));
      camera.updateProjectionMatrix();
    }
  });

  return null;
}
