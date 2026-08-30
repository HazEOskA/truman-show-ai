/**
 * Placing the mission on the real city.
 *
 * The six stations of MISSION 01 are claims about the architecture, and every one of them
 * is pinned to a building the world actually generated — a data centre for the kernel, a
 * factory next to the plant for the economy, a newsroom for information. Nothing is placed
 * at an invented coordinate, so a jury walking the route is walking Hydra's own street plan.
 *
 * The route is then chosen for the walk: stations are spread far enough apart that the city
 * is crossed rather than glanced at, and close enough that the crossing takes seconds.
 */

import type { BuildingView, CityModel } from "@/lib/city/state";
import { STATIONS, type Station } from "@/lib/world3d/mission";

export interface PlayTarget {
  id: string;
  /** Index into `STATIONS` — the station this pylon belongs to. */
  stationIndex: number;
  station: Station;
  label: string;
  buildingIndex: number;
  buildingId: string;
  address: string;
  x: number;
  z: number;
  colour: string;
}

export interface PlayLayout {
  spawn: { x: number; z: number };
  targets: PlayTarget[];
  /** Total walking distance of the route in metres, for the briefing screen. */
  routeMetres: number;
}

/**
 * Which kinds of building each station would rather stand on.
 *
 * A preference, never a requirement: a world whose seed produced no data centre still gets
 * a kernel station, it just stands somewhere less on-the-nose.
 */
const PREFERRED: Record<string, string[]> = {
  kernel: ["data_centre", "transport_hub", "office"],
  genesis: ["city_hall", "school", "university", "office"],
  agents: ["housing"],
  economy: ["factory", "power_plant", "water_plant"],
  information: ["culture", "university", "office"],
  history: ["court", "city_hall", "police", "university"]
};

function distance2(x0: number, z0: number, x1: number, z1: number): number {
  const dx = x0 - x1;
  const dz = z0 - z1;
  return dx * dx + dz * dz;
}

function entranceOf(building: BuildingView): { x: number; z: number } {
  return { x: building.entrance[0], z: building.entrance[1] };
}

/** The agent lands on a street, not inside a wall: the segment nearest the city's centre. */
function nearestStreetSpawn(model: CityModel): { x: number; z: number } {
  const bounds = model.wire.bounds;
  const cx = (bounds.min_x + bounds.max_x) * 0.5;
  const cz = (bounds.min_y + bounds.max_y) * 0.5;
  let best = { x: cx, z: cz };
  let bestD = Number.POSITIVE_INFINITY;
  for (let i = 0; i < model.segmentCount; i += 1) {
    const o = i * 4;
    const x = (model.streetLines[o] + model.streetLines[o + 2]) * 0.5;
    const z = (model.streetLines[o + 1] + model.streetLines[o + 3]) * 0.5;
    const d = distance2(x, z, cx, cz);
    if (d < bestD) {
      bestD = d;
      best = { x, z };
    }
  }
  return best;
}

export function buildPlayLayout(model: CityModel): PlayLayout {
  const spawn = nearestStreetSpawn(model);
  const bounds = model.wire.bounds;
  const span = Math.max(bounds.max_x - bounds.min_x, bounds.max_y - bounds.min_y);
  // Long enough that the jury sees a district change, short enough that nobody is bored.
  const idealStep = Math.max(90, Math.min(420, span * 0.22));
  const minSpacing2 = (idealStep * 0.5) ** 2;

  const used: Array<{ x: number; z: number }> = [];
  const taken = new Set<number>();
  let cursor = spawn;
  const targets: PlayTarget[] = [];
  let routeMetres = 0;

  for (let s = 0; s < STATIONS.length; s += 1) {
    const station = STATIONS[s];
    const kinds = PREFERRED[station.id] ?? [];
    const pick =
      choose(model, kinds, taken, used, cursor, idealStep, minSpacing2) ??
      choose(model, [], taken, used, cursor, idealStep, minSpacing2) ??
      choose(model, [], taken, [], cursor, idealStep, 0);
    if (!pick) continue;

    taken.add(pick.index);
    const point = entranceOf(pick);
    used.push(point);
    routeMetres += Math.hypot(point.x - cursor.x, point.z - cursor.z);
    cursor = point;

    targets.push({
      id: `${station.id}:${pick.id}`,
      stationIndex: s,
      station,
      label: `${station.code} · ${station.title}`,
      buildingIndex: pick.index,
      buildingId: pick.id,
      address: pick.address,
      x: point.x,
      z: point.z,
      colour: station.colour
    });
  }

  return { spawn, targets, routeMetres };
}

/**
 * The best unused building for the next station.
 *
 * Scored on how close its distance from the previous station is to the ideal step, so the
 * route paces itself instead of clustering in whichever corner the generator packed densely.
 */
function choose(
  model: CityModel,
  kinds: string[],
  taken: Set<number>,
  used: Array<{ x: number; z: number }>,
  from: { x: number; z: number },
  idealStep: number,
  minSpacing2: number
): BuildingView | null {
  let best: BuildingView | null = null;
  let bestScore = Number.POSITIVE_INFINITY;

  for (const building of model.buildings) {
    if (taken.has(building.index)) continue;
    if (kinds.length && !kinds.includes(building.kind)) continue;
    const point = entranceOf(building);
    if (used.some((other) => distance2(point.x, point.z, other.x, other.z) < minSpacing2)) continue;
    const step = Math.hypot(point.x - from.x, point.z - from.z);
    const score = Math.abs(step - idealStep);
    if (score < bestScore) {
      bestScore = score;
      best = building;
    }
  }
  return best;
}

export function collidesWithBuilding(model: CityModel, x: number, z: number, radius = 2.4): boolean {
  for (const building of model.buildings) {
    const dx = x - building.x;
    const dz = z - building.y;
    const c = Math.cos(-building.angle);
    const s = Math.sin(-building.angle);
    const lx = dx * c - dz * s;
    const lz = dx * s + dz * c;
    if (
      Math.abs(lx) <= building.width * 0.5 + radius &&
      Math.abs(lz) <= building.depth * 0.5 + radius
    ) return true;
  }
  return false;
}

export function clampToCity(model: CityModel, x: number, z: number, margin = 4): { x: number; z: number } {
  const b = model.wire.bounds;
  return {
    x: Math.max(b.min_x + margin, Math.min(b.max_x - margin, x)),
    z: Math.max(b.min_y + margin, Math.min(b.max_y - margin, z))
  };
}
