/**
 * Getting across Hydra on the streets it actually has.
 *
 * The autopilot's first two attempts steered straight at the next station and fanned the
 * heading aside when something was in the way. Both failed the same way, and the failure is
 * worth writing down because it is not obvious from a diagram: a station stands at a
 * building's *door*, so every leg ends with the agent pressed into an alcove, and from inside
 * one there is no heading toward the next station that is not through a wall. Greedy steering
 * has nothing left to try, and the mission stops on screen in front of the jury.
 *
 * The fix is not a cleverer heuristic. A city is not an open field with obstacles in it — it
 * is a graph, and the projection already carries that graph: street nodes and the segments
 * between them. So the route is planned on the streets, once per leg, and the agent walks the
 * waypoints. It also simply looks right: the agent follows roads instead of scraping along
 * the backs of buildings.
 *
 * The graph is small — a few hundred nodes and a thousand segments — so the search is a plain
 * Dijkstra over an array. There is no need for anything cleverer, and a heap would be more
 * code than the thing it speeds up.
 */

import type { CityModel } from "@/lib/city/state";

export interface StreetGraph {
  /** Node coordinates as [x0, z0, x1, z1, ...] in world metres. */
  points: Float64Array;
  /** For each node, the nodes it shares a street segment with. */
  neighbours: number[][];
}

export interface Point {
  x: number;
  z: number;
}

export function buildStreetGraph(model: CityModel): StreetGraph {
  const nodes = model.wire.streets.nodes;
  const points = new Float64Array(nodes.length);
  points.set(nodes);
  const neighbours: number[][] = Array.from({ length: nodes.length / 2 }, () => []);
  const a = model.wire.streets.a;
  const b = model.wire.streets.b;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] === b[i]) continue;
    neighbours[a[i]].push(b[i]);
    neighbours[b[i]].push(a[i]);
  }
  return { points, neighbours };
}

export function nearestNode(graph: StreetGraph, x: number, z: number): number {
  let best = -1;
  let bestD = Number.POSITIVE_INFINITY;
  for (let i = 0; i < graph.neighbours.length; i += 1) {
    const dx = graph.points[i * 2] - x;
    const dz = graph.points[i * 2 + 1] - z;
    const d = dx * dx + dz * dz;
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

/**
 * Waypoints from one point to another, along the streets.
 *
 * The returned path starts at the street node nearest the origin and ends with the
 * destination itself, so the agent walks out to the road, along it, and then the last few
 * metres to the door. An empty path means the two ends are not connected on the street graph;
 * the caller should fall back to steering straight at the target rather than refusing to move.
 */
export function routeBetween(graph: StreetGraph, from: Point, to: Point): Point[] {
  const count = graph.neighbours.length;
  if (count === 0) return [];
  const start = nearestNode(graph, from.x, from.z);
  const goal = nearestNode(graph, to.x, to.z);
  if (start < 0 || goal < 0) return [];
  if (start === goal) return [nodePoint(graph, goal), { ...to }];

  const distance = new Float64Array(count).fill(Number.POSITIVE_INFINITY);
  const previous = new Int32Array(count).fill(-1);
  const settled = new Uint8Array(count);
  distance[start] = 0;

  for (;;) {
    // Linear scan for the nearest unsettled node. A few hundred nodes make this cheaper in
    // practice than maintaining a heap, and it runs once per leg, not once per frame.
    let current = -1;
    let best = Number.POSITIVE_INFINITY;
    for (let i = 0; i < count; i += 1) {
      if (!settled[i] && distance[i] < best) {
        best = distance[i];
        current = i;
      }
    }
    if (current < 0 || current === goal) break;
    settled[current] = 1;

    for (const next of graph.neighbours[current]) {
      if (settled[next]) continue;
      const dx = graph.points[next * 2] - graph.points[current * 2];
      const dz = graph.points[next * 2 + 1] - graph.points[current * 2 + 1];
      const step = distance[current] + Math.hypot(dx, dz);
      if (step < distance[next]) {
        distance[next] = step;
        previous[next] = current;
      }
    }
  }

  if (!Number.isFinite(distance[goal])) return [];

  const path: Point[] = [];
  for (let node = goal; node >= 0; node = previous[node]) {
    path.push(nodePoint(graph, node));
    if (node === start) break;
  }
  path.reverse();
  path.push({ ...to });
  return path;
}

function nodePoint(graph: StreetGraph, node: number): Point {
  return { x: graph.points[node * 2], z: graph.points[node * 2 + 1] };
}
