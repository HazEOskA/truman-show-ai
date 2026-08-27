"use client";

/**
 * Wiring the City View to a running world.
 *
 * The projection is fetched once and kept; frames arrive on a server-sent event stream and
 * are folded into a single mutable `CityLive`. Deliberately mutable: React re-rendering five
 * thousand agent rows sixty times a second would be a very expensive way to draw a dot, so
 * the live state lives outside React and the renderer reads it directly. React is told only
 * about the things a person looks at -- the clock, the presence counts, the selected panel.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { API_URL, apiGet } from "../api";
import { CityLive, CityModel } from "./state";
import type { CityEvent, FrameWire, LayerMeta, LayerValues, ProjectionWire } from "./types";

export interface CityPulse {
  tick: number;
  simTime: string;
  presence: { observed: number; derived: number; unknown: number; observed_share: number };
  cohortPopulation: number;
  individuals: number;
  connected: boolean;
}

const EMPTY_PULSE: CityPulse = {
  tick: -1,
  simTime: "",
  presence: { observed: 0, derived: 0, unknown: 0, observed_share: 0 },
  cohortPopulation: 0,
  individuals: 0,
  connected: false
};

export function useCityProjection(timelineId: string) {
  const [model, setModel] = useState<CityModel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!timelineId) return;
    let cancelled = false;
    setModel(null);
    setError(null);
    apiGet<ProjectionWire>(`/city/${timelineId}/projection`)
      .then((wire) => {
        if (!cancelled) setModel(new CityModel(wire));
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [timelineId]);

  return { model, error };
}

/**
 * The live stream.
 *
 * Returns a stable `CityLive` the renderer can hold a reference to, plus a small pulse
 * object that React may re-render on. The stream reconnects on its own; a keyframe always
 * arrives first, so a reconnected viewer is never left drawing a stale city.
 */
export function useCityStream(timelineId: string, model: CityModel | null) {
  const liveRef = useRef<CityLive | null>(null);
  const [pulse, setPulse] = useState<CityPulse>(EMPTY_PULSE);

  const live = useMemo(() => {
    if (!model) return null;
    const next = new CityLive(model.buildings.length, model.wire.districts.length);
    liveRef.current = next;
    return next;
  }, [model]);

  useEffect(() => {
    if (!timelineId || !live) return;
    let source: EventSource | null = null;
    let closed = false;
    let raf = 0;
    let dirty = false;

    const publish = () => {
      raf = 0;
      if (!dirty) return;
      dirty = false;
      setPulse({
        tick: live.tick,
        simTime: live.simTime,
        presence: live.presence,
        cohortPopulation: live.cohortPopulation,
        individuals: live.slotOf.size,
        connected: true
      });
    };

    const connect = () => {
      if (closed) return;
      source = new EventSource(`${API_URL}/city/${timelineId}/stream`);
      source.onmessage = (message) => {
        const frame = JSON.parse(message.data) as FrameWire;
        live.apply(frame);
        dirty = true;
        if (!raf) raf = window.requestAnimationFrame(publish);
      };
      source.onerror = () => {
        source?.close();
        setPulse((p) => ({ ...p, connected: false }));
        if (!closed) window.setTimeout(connect, 2000);
      };
    };
    connect();

    return () => {
      closed = true;
      if (raf) window.cancelAnimationFrame(raf);
      source?.close();
    };
  }, [timelineId, live]);

  return { live, pulse };
}

export function useLayers(timelineId: string, layerId: string | null, tick: number) {
  const [catalogue, setCatalogue] = useState<LayerMeta[]>([]);
  const [values, setValues] = useState<Record<string, number> | null>(null);

  useEffect(() => {
    apiGet<{ layers: LayerMeta[] }>("/city/layers")
      .then((data) => setCatalogue(data.layers))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!timelineId || !layerId) {
      setValues(null);
      return;
    }
    let cancelled = false;
    apiGet<LayerValues>(`/city/${timelineId}/layers?ids=${layerId}`)
      .then((data) => {
        if (!cancelled) setValues(data.values[layerId] ?? {});
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // Layers are pulled, not streamed: refresh them when the clock moves, not every frame.
  }, [timelineId, layerId, Math.floor(tick / 6)]);

  const meta = useMemo(
    () => catalogue.find((entry) => entry.id === layerId) ?? null,
    [catalogue, layerId]
  );

  return { catalogue, meta, values };
}

export function useCityEvents(timelineId: string, tick: number) {
  const [events, setEvents] = useState<CityEvent[]>([]);

  useEffect(() => {
    if (!timelineId) return;
    let cancelled = false;
    apiGet<{ events: CityEvent[] }>(`/city/${timelineId}/events?limit=80`)
      .then((data) => {
        if (!cancelled) setEvents(data.events);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [timelineId, Math.floor(tick / 6)]);

  return events;
}

export type InspectTarget = { kind: "building" | "district" | "person"; id: string } | null;

/**
 * The panel behind a click, refreshed as the world moves.
 *
 * `tick` is a dependency on purpose: while a viewer is following someone, the panel has to
 * keep up with them -- their activity, their mood, where they have gone -- or FOLLOW AGENT
 * shows a person frozen at the moment they were selected.
 */
export function useInspector(timelineId: string, tick: number) {
  const [target, setTarget] = useState<InspectTarget>(null);
  const [detail, setDetail] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(false);

  const inspect = useCallback((next: InspectTarget) => {
    setTarget(next);
    setDetail(null);
  }, []);

  useEffect(() => {
    if (!timelineId || !target || target.kind === "district") return;
    const path =
      target.kind === "building"
        ? `/city/${timelineId}/building/${target.id}`
        : `/city/${timelineId}/agent/${target.id}`;
    let cancelled = false;
    setLoading(true);
    apiGet<Record<string, any>>(path)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [timelineId, target?.kind, target?.id, tick]);

  return { target, detail, loading, inspect };
}
