"use client";

/**
 * Hydra City View.
 *
 * The Observatory's other pages tell you that Hydra is alive. This one shows you.
 *
 * Everything on screen is read from the running world: the ground plan comes from the
 * spatial projection, the people come from the frame stream, and the panels come from the
 * same state the simulation is using. Nothing is generated here. The one thing this page
 * adds on its own is the honesty readout in the header, which says how much of the crowd is
 * observed and how much is inferred -- and lets you switch the inferred half off.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import "./city.css";

import WorldPicker from "@/components/WorldPicker";
import { useSelection } from "@/lib/api";
import { CityRenderer, type PickResult } from "@/lib/city/renderer";
import {
  useCityEvents,
  useCityProjection,
  useCityStream,
  useInspector,
  useLayers
} from "@/lib/city/useCity";
import { Lod } from "@/lib/city/camera";

const LOD_LABEL: Record<number, string> = {
  [Lod.Region]: "region",
  [Lod.Quarter]: "quarters",
  [Lod.Street]: "streets",
  [Lod.Close]: "close"
};

export default function CityPage() {
  const { worldId, timelineId, select } = useSelection();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rendererRef = useRef<CityRenderer | null>(null);

  const { model, error } = useCityProjection(timelineId);
  const { live, pulse } = useCityStream(timelineId, model);
  const [layerId, setLayerId] = useState<string | null>(null);
  const { catalogue, meta, values } = useLayers(timelineId, layerId, pulse.tick);
  const events = useCityEvents(timelineId, pulse.tick);
  const { target, detail, inspect } = useInspector(timelineId, pulse.tick);

  const [showDerived, setShowDerived] = useState(true);
  const [showCohorts, setShowCohorts] = useState(true);
  const [following, setFollowing] = useState<string | null>(null);
  const [stats, setStats] = useState({ fps: 0, lod: Lod.Region, drawMs: 0, width: 0, height: 0 });

  // -- renderer lifecycle ---------------------------------------------------------

  const onPick = useCallback(
    (hit: PickResult | null) => {
      rendererRef.current?.select(hit);
      inspect(hit ? { kind: hit.kind, id: hit.id } : null);
    },
    [inspect]
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const renderer = new CityRenderer();
    rendererRef.current = renderer;
    let cancelled = false;
    renderer.attach(canvas, { onPick }).catch(() => undefined);
    const timer = window.setInterval(() => {
      if (!cancelled) setStats(renderer.stats);
    }, 500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      renderer.detach();
      rendererRef.current = null;
    };
  }, [onPick]);

  useEffect(() => {
    if (model) rendererRef.current?.setModel(model);
  }, [model]);

  useEffect(() => {
    if (live) rendererRef.current?.setLive(live);
  }, [live]);

  useEffect(() => {
    rendererRef.current?.setLayer(meta && values ? { meta, values } : null);
  }, [meta, values]);

  useEffect(() => {
    rendererRef.current?.setEvents(events);
  }, [events]);

  useEffect(() => {
    rendererRef.current?.setDerivedVisible(showDerived);
  }, [showDerived]);

  useEffect(() => {
    rendererRef.current?.setCohortsVisible(showCohorts);
  }, [showCohorts]);

  useEffect(() => {
    rendererRef.current?.follow(following);
  }, [following]);

  // -- derived readouts -----------------------------------------------------------

  const observedPct = Math.round(pulse.presence.observed_share * 100);
  const derivedCount = pulse.presence.derived;
  const districtLayers = catalogue.filter((l) => l.scope === "district");
  const buildingLayers = catalogue.filter((l) => l.scope === "building");

  const followName = useMemo(() => {
    if (!following) return null;
    if (detail && detail.person_id === following) return detail.name as string;
    return following;
  }, [following, detail]);

  return (
    <div className="city">
      <header className="city-bar">
        <div className="city-clock">
          <strong>{pulse.simTime || "—"}</strong>
          <span className={pulse.connected ? "live" : "stale"}>
            {pulse.connected ? "live" : "reconnecting"} · tick {pulse.tick >= 0 ? pulse.tick : "—"}
          </span>
        </div>

        <div className="city-honesty" title="How much of what you see is stated by the world">
          <span className="ok">{pulse.presence.observed.toLocaleString()} observed</span>
          <span className="inferred">{derivedCount.toLocaleString()} inferred</span>
          <div className="honesty-bar">
            <div className="honesty-fill" style={{ width: `${observedPct}%` }} />
          </div>
          <small>
            {observedPct}% of positions come from world state. Hydra does not simulate the
            commute, so a worker still recorded at home during their shift is drawn at work and
            marked.
          </small>
        </div>

        <div className="city-counts">
          <span>{pulse.individuals.toLocaleString()} individuals</span>
          <span className="muted">{pulse.cohortPopulation.toLocaleString()} in cohorts</span>
        </div>

        <WorldPicker worldId={worldId} timelineId={timelineId} onSelect={select} />
      </header>

      <div className="city-body">
        <aside className="city-panel">
          <section>
            <h3>Layers</h3>
            <button
              className={layerId === null ? "chip active" : "chip"}
              onClick={() => setLayerId(null)}
            >
              None
            </button>
            <div className="chips">
              {districtLayers.map((entry) => (
                <button
                  key={entry.id}
                  className={layerId === entry.id ? "chip active" : "chip"}
                  title={`reads ${entry.source}`}
                  onClick={() => setLayerId(entry.id)}
                >
                  {entry.label}
                </button>
              ))}
            </div>
            <h4>Buildings</h4>
            <div className="chips">
              {buildingLayers.map((entry) => (
                <button
                  key={entry.id}
                  className={layerId === entry.id ? "chip active" : "chip"}
                  title={`reads ${entry.source}`}
                  onClick={() => setLayerId(entry.id)}
                >
                  {entry.label}
                </button>
              ))}
            </div>
            {meta && (
              <p className="legend">
                <span>{meta.label}</span>
                <small>
                  {meta.low} – {meta.high} {meta.unit} · from <code>{meta.source}</code>
                </small>
              </p>
            )}
          </section>

          <section>
            <h3>Show</h3>
            <label>
              <input
                type="checkbox"
                checked={showDerived}
                onChange={(e) => setShowDerived(e.target.checked)}
              />
              Inferred positions
            </label>
            <label>
              <input
                type="checkbox"
                checked={showCohorts}
                onChange={(e) => setShowCohorts(e.target.checked)}
              />
              Cohort density
            </label>
            <button className="chip" onClick={() => rendererRef.current?.frameCity()}>
              Frame the city
            </button>
          </section>

          <section className="city-stats">
            <h3>Render</h3>
            <div>
              {stats.fps} fps · {LOD_LABEL[stats.lod]} · {stats.drawMs} ms/frame
            </div>
            <div className="muted">
              viewport {stats.width}×{stats.height}
            </div>
            {model && (
              <div className="muted">
                {model.buildings.length} buildings · {model.segmentCount} street segments
              </div>
            )}
          </section>
        </aside>

        <div className="city-stage">
          {error && <div className="city-error">No city yet: {error}</div>}
          {!model && !error && <div className="city-loading">Projecting Hydra…</div>}
          <canvas ref={canvasRef} className="city-canvas" />
        </div>

        <aside className={target ? "city-inspector open" : "city-inspector"}>
          {!target && <p className="muted">Click a building or a person.</p>}

          {target?.kind === "building" && detail && (
            <BuildingPanel
              detail={detail}
              onPerson={(id) => inspect({ kind: "person", id })}
            />
          )}

          {target?.kind === "person" && detail && (
            <PersonPanel
              detail={detail}
              following={following === detail.person_id}
              onFollow={() =>
                setFollowing(following === detail.person_id ? null : (detail.person_id as string))
              }
              onBuilding={(id) => {
                inspect({ kind: "building", id });
                rendererRef.current?.focusBuilding(id);
              }}
            />
          )}

          {target?.kind === "district" && (
            <div>
              <h3>{target.id}</h3>
              <p className="muted">
                Pick a layer to colour the quarters, or click a building inside it.
              </p>
            </div>
          )}

          {followName && (
            <div className="following">
              Following <strong>{followName}</strong>
              <button className="chip" onClick={() => setFollowing(null)}>
                Stop
              </button>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function BuildingPanel({
  detail,
  onPerson
}: {
  detail: Record<string, any>;
  onPerson: (id: string) => void;
}) {
  return (
    <div>
      <h3>{detail.name || detail.building_id}</h3>
      <div className="kv">
        <span>Kind</span>
        <b>{detail.kind}</b>
        <span>Address</span>
        <b>{detail.address || "—"}</b>
        <span>Quarter</span>
        <b>{detail.district?.name || detail.district?.id}</b>
        <span>Occupancy</span>
        <b>
          {detail.occupancy} / {detail.capacity}
        </b>
        <span>Condition</span>
        <b>{Math.round((detail.condition ?? 0) * 100)}%</b>
        <span>Owner</span>
        <b>{detail.owner?.name || "—"}</b>
      </div>

      <h4>
        Here now ({detail.people_here_total})
        <small className="muted"> · {detail.observed_here} observed</small>
      </h4>
      <ul className="people">
        {(detail.people_here ?? []).map((person: Record<string, any>) => (
          <li key={person.person_id}>
            <button className="link" onClick={() => onPerson(person.person_id)}>
              {person.name}
            </button>
            <span className={person.position_source === "observed" ? "tag ok" : "tag inferred"}>
              {person.activity}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PersonPanel({
  detail,
  following,
  onFollow,
  onBuilding
}: {
  detail: Record<string, any>;
  following: boolean;
  onFollow: () => void;
  onBuilding: (id: string) => void;
}) {
  const source = detail.position?.source as string;
  return (
    <div>
      <h3>{detail.name}</h3>
      <div className="row">
        <span className={detail.awake ? "tag ok" : "tag asleep"}>{detail.activity}</span>
        <span className="tag">tier {detail.tier}</span>
        <span className={source === "observed" ? "tag ok" : "tag inferred"}>{source}</span>
      </div>

      <button className={following ? "chip active" : "chip"} onClick={onFollow}>
        {following ? "Following" : "Follow"}
      </button>

      <div className="kv">
        <span>Age</span>
        <b>{detail.age}</b>
        <span>Work</span>
        <b>{detail.occupation}</b>
        <span>Employment</span>
        <b>{detail.employment}</b>
        <span>Wage</span>
        <b>{detail.wage}</b>
        <span>Mood</span>
        <b>{detail.mood}</b>
        <span>Energy</span>
        <b>{detail.energy}</b>
        <span>Stress</span>
        <b>{detail.stress}</b>
      </div>

      <h4>Where</h4>
      <div className="places">
        {["at", "home", "work"].map((slot) =>
          detail[slot] ? (
            <button key={slot} className="link" onClick={() => onBuilding(detail[slot].building_id)}>
              <b>{slot}</b> {detail[slot].address || detail[slot].name || detail[slot].building_id}
            </button>
          ) : null
        )}
      </div>

      {detail.last_action && (
        <>
          <h4>Doing</h4>
          <p>{detail.last_action}</p>
        </>
      )}

      {(detail.goals ?? []).length > 0 && (
        <>
          <h4>Goals</h4>
          <ul className="goals">
            {detail.goals.map((goal: Record<string, any>, i: number) => (
              <li key={i}>
                {goal.label}
                <em>{Math.round(goal.progress * 100)}%</em>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
