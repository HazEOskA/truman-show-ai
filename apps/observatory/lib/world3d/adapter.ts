import type { BuildingView, CityModel } from "@/lib/city/state";

export type ObjectiveKind = "terminal" | "contact" | "relay";

export interface PlayTarget {
  id: string;
  label: string;
  kind: ObjectiveKind;
  buildingIndex: number;
  x: number;
  z: number;
  color: string;
}

export interface PlayLayout {
  spawn: { x: number; z: number };
  targets: PlayTarget[];
}

function distance2(x0: number, z0: number, x1: number, z1: number): number {
  const dx = x0 - x1;
  const dz = z0 - z1;
  return dx * dx + dz * dz;
}

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

function entranceOf(building: BuildingView): { x: number; z: number } {
  return { x: building.entrance[0], z: building.entrance[1] };
}

export function buildPlayLayout(model: CityModel): PlayLayout {
  const spawn = nearestStreetSpawn(model);
  const byDistance = [...model.buildings].sort((a, b) => {
    const ea = entranceOf(a);
    const eb = entranceOf(b);
    return distance2(ea.x, ea.z, spawn.x, spawn.z) - distance2(eb.x, eb.z, spawn.x, spawn.z);
  });

  const picked: BuildingView[] = [];
  const minSpacing2 = 55 * 55;
  for (const candidate of byDistance) {
    const p = entranceOf(candidate);
    const farEnough = picked.every((other) => {
      const q = entranceOf(other);
      return distance2(p.x, p.z, q.x, q.z) >= minSpacing2;
    });
    if (farEnough) picked.push(candidate);
    if (picked.length === 4) break;
  }
  while (picked.length < 4 && byDistance[picked.length]) picked.push(byDistance[picked.length]);

  const defs: Array<[ObjectiveKind, string, string]> = [
    ["terminal", "play.objective.terminal", "#39e6ff"],
    ["contact", "play.objective.vekt", "#3cffd4"],
    ["contact", "play.objective.lumen", "#d18bff"],
    ["relay", "play.objective.relay", "#ffe14d"]
  ];

  const targets = picked.map((building, index) => {
    const [kind, label, color] = defs[index] ?? defs[defs.length - 1];
    const point = entranceOf(building);
    return {
      id: `${kind}:${building.id}`,
      label,
      kind,
      buildingIndex: building.index,
      x: point.x,
      z: point.z,
      color
    } satisfies PlayTarget;
  });

  return { spawn, targets };
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
