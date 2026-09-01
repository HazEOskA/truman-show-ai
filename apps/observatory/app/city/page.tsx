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
import { useI18n } from "@/components/I18n";
import { useSelection } from "@/lib/api";
import { CityRenderer, type PickResult } from "@/lib/city/renderer";
import {
  useCauses,
  useCityEvents,
  useCityProjection,
  useCityStream,
  useClock,
  useInspector,
  useLayers,
  useScenarios
} from "@/lib/city/useCity";
import { Lod } from "@/lib/city/camera";
import type { CityEvent } from "@/lib/city/types";

const LOD_LABEL: Record<number, string> = {
  [Lod.Region]: "city.lod.region",
  [Lod.Quarter]: "city.lod.quarters",
  [Lod.Street]: "city.lod.streets",
  [Lod.Close]: "city.lod.close"
};

export default function CityPage() {
  const { t, term } = useI18n();
  const { worldId, timelineId, select } = useSelection();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rendererRef = useRef<CityRenderer | null>(null);

  const { model, error } = useCityProjection(timelineId);
  const { live, pulse } = useCityStream(timelineId, model);
  const [layerId, setLayerId] = useState<string | null>(null);
  const { catalogue, meta, values } = useLayers(timelineId, layerId, pulse.tick);
  const events = useCityEvents(timelineId, pulse.tick);
  const { target, detail, inspect } = useInspector(timelineId, pulse.tick);
  const clock = useClock(worldId, timelineId, pulse.tick);
  const scenarios = useScenarios(worldId, timelineId);
  const [eventId, setEventId] = useState<string | null>(null);
  const { chain } = useCauses(worldId, timelineId, eventId);

  const [showDerived, setShowDerived] = useState(true);
  const [showCohorts, setShowCohorts] = useState(true);
  const [following, setFollowing] = useState<string | null>(null);
  const [stats, setStats] = useState({ fps: 0, lod: Lod.Region, drawMs: 0, width: 0, height: 0 });

  // -- renderer lifecycle ---------------------------------------------------------

  const onPick = useCallback(
    (hit: PickResult | null) => {
      rendererRef.current?.select(hit);
      setEventId(null);
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
            {pulse.connected ? t("city.live") : t("city.reconnecting")} · {t("common.tick")} {pulse.tick >= 0 ? pulse.tick : "—"}
          </span>
        </div>

        <div className="city-honesty" title={t("city.honestyTitle")}>
          <span className="ok">{pulse.presence.observed.toLocaleString()} {t("city.observed")}</span>
          <span className="inferred">{derivedCount.toLocaleString()} {t("city.inferred")}</span>
          <div className="honesty-bar">
            <div className="honesty-fill" style={{ width: `${observedPct}%` }} />
          </div>
          <small>
            {t("city.honestyCopy", { value: observedPct })}
          </small>
        </div>

        <div className="city-counts">
          <span>{t("city.individuals", { count: pulse.individuals.toLocaleString() })}</span>
          <span className="muted">{t("city.cohorts", { count: pulse.cohortPopulation.toLocaleString() })}</span>
        </div>

        <WorldPicker worldId={worldId} timelineId={timelineId} onSelect={select} />
      </header>

      <div className="city-body">
        <aside className="city-panel">
          <section>
            <h3>{t("city.layers")}</h3>
            <button
              className={layerId === null ? "chip active" : "chip"}
              onClick={() => setLayerId(null)}
            >
              {t("common.none")}
            </button>
            <div className="chips">
              {districtLayers.map((entry) => (
                <button
                  key={entry.id}
                  className={layerId === entry.id ? "chip active" : "chip"}
                  title={t("city.reads", { source: entry.source })}
                  onClick={() => setLayerId(entry.id)}
                >
                  {term(entry.label)}
                </button>
              ))}
            </div>
            <h4>{t("city.buildings")}</h4>
            <div className="chips">
              {buildingLayers.map((entry) => (
                <button
                  key={entry.id}
                  className={layerId === entry.id ? "chip active" : "chip"}
                  title={t("city.reads", { source: entry.source })}
                  onClick={() => setLayerId(entry.id)}
                >
                  {term(entry.label)}
                </button>
              ))}
            </div>
            {meta && (
              <p className="legend">
                <span>{term(meta.label)}</span>
                <small>
                  {meta.low} – {meta.high} {meta.unit} · {t("city.from", { source: meta.source })}
                </small>
              </p>
            )}
          </section>

          <section>
            <h3>{t("city.show")}</h3>
            <label>
              <input
                type="checkbox"
                checked={showDerived}
                onChange={(e) => setShowDerived(e.target.checked)}
              />
              {t("city.inferredPositions")}
            </label>
            <label>
              <input
                type="checkbox"
                checked={showCohorts}
                onChange={(e) => setShowCohorts(e.target.checked)}
              />
              {t("city.cohortDensity")}
            </label>
            <button className="chip" onClick={() => rendererRef.current?.frameCity()}>
              {t("city.frame")}
            </button>
          </section>

          <section>
            <h3>{t("city.time")}</h3>
            <div className="chips">
              <button
                className={clock.running ? "chip active" : "chip"}
                onClick={() => (clock.running ? clock.pause() : clock.play())}
                disabled={clock.busy || !worldId}
              >
                {clock.running ? t("city.pause") : t("city.play")}
              </button>
              <button className="chip" onClick={() => clock.step(6)} disabled={clock.busy || !worldId}>
                {t("city.hour")}
              </button>
              <button className="chip" onClick={() => clock.step(144)} disabled={clock.busy || !worldId}>
                {t("city.day")}
              </button>
            </div>
            <div className="chips" style={{ marginTop: 6 }}>
              {[1, 2, 4, 12].map((speed) => (
                <button
                  key={speed}
                  className={clock.control?.speed === speed ? "chip active" : "chip"}
                  onClick={() => clock.setSpeed(speed)}
                  disabled={clock.busy || !worldId}
                >
                  ×{speed}
                </button>
              ))}
            </div>
            {clock.control?.note && <p className="legend"><small>{clock.control.note}</small></p>}
          </section>

          <section>
            <h3>{t("city.shock")}</h3>
            <div className="chips">
              {scenarios.names.map((name) => (
                <button
                  key={name}
                  className="chip"
                  onClick={() => scenarios.fire(name)}
                  disabled={!worldId}
                  title={t("city.scenarioTitle")}
                >
                  {term(name)}
                </button>
              ))}
            </div>
            {scenarios.queued && (
              <p className="legend">
                <small>{t("city.queued", { name: term(scenarios.queued) })}</small>
              </p>
            )}
          </section>

          <section className="city-stats">
            <h3>{t("city.render")}</h3>
            <div>
              {stats.fps} fps · {t(LOD_LABEL[stats.lod])} · {stats.drawMs} ms/frame
            </div>
            <div className="muted">
              {t("city.viewport", { width: stats.width, height: stats.height })}
            </div>
            {model && (
              <div className="muted">
                {t("city.modelStats", { buildings: model.buildings.length, segments: model.segmentCount })}
              </div>
            )}
          </section>
        </aside>

        <div className="city-stage">
          {error && <div className="city-error">{t("city.noCity", { error })}</div>}
          {!model && !error && <div className="city-loading">{t("city.projecting")}</div>}
          <canvas ref={canvasRef} className="city-canvas" />
        </div>

        <aside className={target || eventId ? "city-inspector open" : "city-inspector"}>
          {!target && !eventId && (
            <EventFeed events={events} onPick={(id, anchor) => {
              setEventId(id);
              inspect(null);
              if (anchor) rendererRef.current?.lookAt(anchor[0], anchor[1]);
            }} />
          )}

          {eventId && !target && (
            <CausePanel
              chain={chain}
              onBack={() => setEventId(null)}
              onEvent={(id) => setEventId(id)}
            />
          )}

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
                {t("city.pickHint")}
              </p>
            </div>
          )}

          {followName && (
            <div className="following">
              {t("city.following")} <strong>{followName}</strong>
              <button className="chip" onClick={() => setFollowing(null)}>
                {t("city.stop")}
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
  const { t, term } = useI18n();
  return (
    <div>
      <h3>{detail.name || detail.building_id}</h3>
      <div className="kv">
        <span>{t("common.kind")}</span>
        <b>{term(detail.kind)}</b>
        <span>{t("city.address")}</span>
        <b>{detail.address || "—"}</b>
        <span>{t("city.quarter")}</span>
        <b>{detail.district?.name || detail.district?.id}</b>
        <span>{t("city.occupancy")}</span>
        <b>
          {detail.occupancy} / {detail.capacity}
        </b>
        <span>{t("city.condition")}</span>
        <b>{Math.round((detail.condition ?? 0) * 100)}%</b>
        <span>{t("city.owner")}</span>
        <b>{detail.owner?.name || "—"}</b>
      </div>

      <h4>
        {t("city.hereNow", { count: detail.people_here_total })}
        <small className="muted"> · {t("city.observedHere", { count: detail.observed_here })}</small>
      </h4>
      <ul className="people">
        {(detail.people_here ?? []).map((person: Record<string, any>) => (
          <li key={person.person_id}>
            <button className="link" onClick={() => onPerson(person.person_id)}>
              {person.name}
            </button>
            <span className={person.position_source === "observed" ? "tag ok" : "tag inferred"}>
              {term(person.activity)}
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
  const { t, term } = useI18n();
  const source = detail.position?.source as string;
  return (
    <div>
      <h3>{detail.name}</h3>
      <div className="row">
        <span className={detail.awake ? "tag ok" : "tag asleep"}>{term(detail.activity)}</span>
        <span className="tag">{t("people.tier")} {detail.tier}</span>
        <span className={source === "observed" ? "tag ok" : "tag inferred"}>{term(source)}</span>
      </div>

      <button className={following ? "chip active" : "chip"} onClick={onFollow}>
        {following ? t("city.following") : t("city.follow")}
      </button>

      <div className="kv">
        <span>{t("city.age")}</span>
        <b>{detail.age}</b>
        <span>{t("city.work")}</span>
        <b>{term(detail.occupation)}</b>
        <span>{t("city.employment")}</span>
        <b>{term(detail.employment)}</b>
        <span>{t("city.wage")}</span>
        <b>{detail.wage}</b>
        <span>{t("person.mood")}</span>
        <b>{detail.mood}</b>
        <span>{t("person.energy")}</span>
        <b>{detail.energy}</b>
        <span>{t("person.stress")}</span>
        <b>{detail.stress}</b>
      </div>

      <h4>{t("city.where")}</h4>
      <div className="places">
        {["at", "home", "work"].map((slot) =>
          detail[slot] ? (
            <button key={slot} className="link" onClick={() => onBuilding(detail[slot].building_id)}>
              <b>{term(slot)}</b> {detail[slot].address || detail[slot].name || detail[slot].building_id}
            </button>
          ) : null
        )}
      </div>

      {detail.last_action && (
        <>
          <h4>{t("city.doing")}</h4>
          <p>{detail.last_action}</p>
        </>
      )}

      {(detail.goals ?? []).length > 0 && (
        <>
          <h4>{t("city.goals")}</h4>
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

/**
 * What just happened, in the order it happened.
 *
 * This is the inspector's resting state on purpose. An empty panel saying "click something"
 * wastes the one piece of screen that could be telling you the city is alive; a feed of real
 * events, each one clickable through to its causes, does the opposite.
 */
function EventFeed({
  events,
  onPick
}: {
  events: CityEvent[];
  onPick: (id: string, anchor: [number, number] | null) => void;
}) {
  const { t, term } = useI18n();
  if (!events.length) {
    return <p className="muted">{t("city.nothing")}</p>;
  }
  return (
    <div>
      <h3>{t("city.happening")}</h3>
      <ul className="feed">
        {events.map((event) => (
          <li key={event.event_id}>
            <button className="link" onClick={() => onPick(event.event_id, event.anchor)}>
              {event.headline || term(event.action)}
            </button>
            <div className="feed-meta">
              <span>{event.sim_time || `t${event.tick}`}</span>
              <span className={`tag ${event.anchor_kind === "building" ? "ok" : ""}`}>
                {event.anchor_kind === "none" ? t("city.cityWide") : term(event.anchor_kind)}
              </span>
              {event.importance >= 0.5 && <span className="tag inferred">{t("city.major")}</span>}
              {/* Most events are their own root. Marking the ones with a recorded cause
                  saves a viewer from clicking through to "nothing caused this" repeatedly. */}
              {event.causes.length > 0 && <span className="tag ok">{t("city.why")}</span>}
              {/* Which paper said it, and how it chose to say it. Hydra's outlets have
                  owners and slants, and the same event reaches people as several stories. */}
              {event.outlet && <span className="tag">{event.outlet}</span>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Why it happened.
 *
 * The chain is not reconstructed here or anywhere else: the kernel recorded each link when
 * the event fired. That is the difference between a simulation that can be asked why and a
 * story that has been written to look like one.
 */
function CausePanel({
  chain,
  onBack,
  onEvent
}: {
  chain: Record<string, any> | null;
  onBack: () => void;
  onEvent: (id: string) => void;
}) {
  const { t, term } = useI18n();
  if (!chain) return <p className="muted">{t("city.readingCauses")}</p>;
  const event = chain.event as Record<string, any> | null;
  if (!event) {
    return (
      <div>
        <button className="chip" onClick={onBack}>{t("common.back")}</button>
        <p className="muted">{t("city.eventGone")}</p>
      </div>
    );
  }

  const causes = (chain.chain ?? []) as Record<string, any>[];
  const effects = (chain.consequences ?? []) as Record<string, any>[];

  return (
    <div>
      <button className="chip" onClick={onBack}>{t("common.back")}</button>
      <h3>{term(event.action)}</h3>
      <div className="kv">
        <span>{t("city.when")}</span>
        <b>{event.sim_time || `tick ${event.tick}`}</b>
        <span>{t("common.topic")}</span>
        <b>{term(event.topic)}</b>
        <span>{t("city.whereLabel")}</span>
        <b>{event.location || t("city.cityWide")}</b>
        <span>{t("city.importance")}</span>
        <b>{Math.round((event.importance ?? 0) * 100)}%</b>
      </div>

      <h4>{t("city.because", { count: causes.length })}</h4>
      {causes.length === 0 && <p className="muted">{t("city.root")}</p>}
      <ul className="feed">
        {causes.map((node, i) => (
          <li key={i}>
            <button className="link" onClick={() => onEvent(node.event.event_id)}>
              {"→ ".repeat(Math.min(3, node.depth))}
              {term(node.event.action)}
            </button>
            <div className="feed-meta">
              <span>{node.event.sim_time || `t${node.event.tick}`}</span>
              <span>{term(node.event.topic)}</span>
            </div>
          </li>
        ))}
      </ul>

      <h4>{t("city.then", { count: effects.length })}</h4>
      {effects.length === 0 && <p className="muted">{t("city.noEffects")}</p>}
      <ul className="feed">
        {effects.slice(0, 12).map((node, i) => (
          <li key={i}>
            <button className="link" onClick={() => onEvent(node.event.event_id)}>
              {term(node.event.action)}
            </button>
            <div className="feed-meta">
              <span>{node.event.sim_time || `t${node.event.tick}`}</span>
              <span>{term(node.event.topic)}</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
