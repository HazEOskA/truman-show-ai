/**
 * The shapes the City View API sends.
 *
 * These mirror `hydra.viewmodel.wire` and `hydra.viewmodel.frames` exactly. Everything is
 * columnar and index-based: a building is a position in `order.buildings`, an activity is a
 * position in `codes.activity`. Nothing here is a domain object, because the renderer is
 * never given one -- it draws what the view model says and nothing else.
 */

export type Vec2 = [number, number];

export interface Bounds {
  min_x: number;
  min_y: number;
  max_x: number;
  max_y: number;
}

export interface DistrictWire {
  id: string;
  name: string;
  kind: string;
  /** Flat [x0, y0, x1, y1, ...] in metres. */
  polygon: number[];
  /** The built-up part, where streets and buildings actually are. */
  built: number[];
  centre: Vec2;
  area_m2: number;
  angle: number;
  block_m: number;
}

export interface StreetsWire {
  /** Flat node coordinates, [x0, y0, x1, y1, ...]. */
  nodes: number[];
  a: number[];
  b: number[];
  /** Index into `klasses`. */
  klass: number[];
  width: number[];
  /** Index into `street_names`, or -1. */
  name: number[];
  klasses: string[];
}

/** Rectangles arrive as [x, y, width, depth, angle] per item, flattened. */
export type RectArray = number[];

export interface ParcelsWire {
  rect: RectArray;
  use: number[];
  district: number[];
  uses: string[];
}

export interface BuildingsWire {
  rect: RectArray;
  kind: string[];
  floors: number[];
  height: number[];
  district: number[];
  parcel: number[];
  /** Flat [x, y] per building. */
  entrance: number[];
  address: string[];
}

export interface TransitLineWire {
  id: string;
  name: string;
  colour: string;
  path: number[];
  stops: string[];
}

export interface TransitStopWire {
  id: string;
  name: string;
  point: Vec2;
  district: number;
}

export interface ProjectionWire {
  projection_hash: string;
  projection_version: string;
  city_id: string;
  bounds: Bounds;
  boundary: number[];
  order: { buildings: string[]; districts: string[] };
  districts: DistrictWire[];
  streets: StreetsWire;
  parcels: ParcelsWire;
  buildings: BuildingsWire;
  transit: { lines: TransitLineWire[]; stops: TransitStopWire[] };
  street_names: string[];
  report: Record<string, unknown>;
}

export interface PresenceWire {
  observed: number;
  derived: number;
  unknown: number;
  observed_share: number;
}

export interface FrameWire {
  kind: "keyframe" | "delta";
  tick: number;
  timeline_id: string;
  sim_time: string;
  agents: { id: string[]; b: number[]; s: number[]; a: number[]; t: number[] };
  gone: string[];
  buildings: { i: number[]; occupancy: number[]; awake: number[]; condition: number[] };
  districts: { i: number[]; population: number[]; asleep: number[]; unrest: number[]; power: number[] };
  presence: PresenceWire;
  cohort_population: number;
  codes: { activity: string[]; source: string[]; tier: string[] };
}

export interface LayerMeta {
  id: string;
  label: string;
  scope: "district" | "building";
  unit: string;
  low: number;
  high: number;
  high_is_bad: boolean;
  source: string;
}

export interface LayerValues {
  tick: number;
  catalogue: LayerMeta[];
  values: Record<string, Record<string, number>>;
}

export interface CityEvent {
  event_id: string;
  tick: number;
  sim_time: string;
  topic: string;
  action: string;
  headline: string;
  importance: number;
  actor: string | null;
  target: string | null;
  district_id: string;
  building_id: string;
  anchor: Vec2 | null;
  anchor_kind: "building" | "district" | "none";
  causes: string[];
  effects: string[];
}

/** Wire codes, kept in sync with `hydra.viewmodel.frames`. */
export const ACTIVITY = { ACTIVE: 0, LIGHT_IDLE: 1, SLEEP: 2, DORMANT: 3, OFFSCREEN: 4 } as const;
export const SOURCE = { OBSERVED: 0, DERIVED: 1, UNKNOWN: 2 } as const;
export const TIER = { PERSISTENT: 0, LIGHTWEIGHT: 1, COHORT: 2 } as const;
