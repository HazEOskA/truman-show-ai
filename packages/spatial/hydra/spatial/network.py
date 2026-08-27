"""Stage 5 -- routing and transit.

The street graph from stage 2 is already the routing network; this stage adds the two things
that make it usable: a shortest-path function, and public transport lines that follow real
streets instead of being drawn as straight lines between icons.

Routing lives here rather than in the renderer on purpose. A path between two buildings is a
fact about the city's geometry, identical for every viewer, so it belongs to the projection
and is computed once -- not recomputed in every browser, differently.
"""

from __future__ import annotations

import heapq
import math
from typing import Sequence

from . import geometry as g
from .model import (
    BuildingPlacement,
    DistrictShape,
    StreetClass,
    StreetNetwork,
    TransitLine,
    TransitStop,
    Vec2,
)

LINE_COLOURS = ("#4bd6ff", "#ff5cc8", "#a970ff", "#ffc857", "#5ce68a")
#: Arterials and collectors are what transit runs on; local streets are too small.
TRANSIT_PENALTY = {StreetClass.ARTERIAL: 1.0, StreetClass.COLLECTOR: 1.25, StreetClass.LOCAL: 2.6}


def shortest_path(network: StreetNetwork, start: str, goal: str) -> list[str]:
    """Dijkstra over segment lengths. Returns node ids, empty if unreachable."""

    if start == goal:
        return [start] if start in network.nodes else []
    if start not in network.nodes or goal not in network.nodes:
        return []

    best: dict[str, float] = {start: 0.0}
    previous: dict[str, str] = {}
    queue: list[tuple[float, str]] = [(0.0, start)]
    settled: set[str] = set()

    while queue:
        cost, node = heapq.heappop(queue)
        if node in settled:
            continue
        settled.add(node)
        if node == goal:
            break
        for neighbour, _segment, length in network.adjacency.get(node, ()):
            if neighbour in settled:
                continue
            candidate = cost + length
            if candidate < best.get(neighbour, math.inf):
                best[neighbour] = candidate
                previous[neighbour] = node
                heapq.heappush(queue, (candidate, neighbour))

    if goal not in previous and goal != start:
        return []
    path = [goal]
    while path[-1] != start:
        step = previous.get(path[-1])
        if step is None:
            return []
        path.append(step)
    path.reverse()
    return path


def transit_path(network: StreetNetwork, start: str, goal: str) -> list[str]:
    """Like :func:`shortest_path` but biased onto roads a bus would actually use."""

    if start not in network.nodes or goal not in network.nodes:
        return []
    best: dict[str, float] = {start: 0.0}
    previous: dict[str, str] = {}
    queue: list[tuple[float, str]] = [(0.0, start)]
    settled: set[str] = set()

    while queue:
        cost, node = heapq.heappop(queue)
        if node in settled:
            continue
        settled.add(node)
        if node == goal:
            break
        for neighbour, segment_id, length in network.adjacency.get(node, ()):
            if neighbour in settled:
                continue
            segment = network.segments.get(segment_id)
            weight = TRANSIT_PENALTY.get(segment.klass, 2.0) if segment else 2.0
            candidate = cost + length * weight
            if candidate < best.get(neighbour, math.inf):
                best[neighbour] = candidate
                previous[neighbour] = node
                heapq.heappush(queue, (candidate, neighbour))

    if goal == start:
        return [start]
    if goal not in previous:
        return []
    path = [goal]
    while path[-1] != start:
        step = previous.get(path[-1])
        if step is None:
            return []
        path.append(step)
    path.reverse()
    return path


def path_points(network: StreetNetwork, path: Sequence[str]) -> list[Vec2]:
    return [network.nodes[n].point for n in path if n in network.nodes]


def build_transit(
    seed: int,
    shapes: dict[str, DistrictShape],
    network: StreetNetwork,
    placements: dict[str, BuildingPlacement],
) -> tuple[dict[str, TransitStop], dict[str, TransitLine], dict[str, object]]:
    """Two cross-city lines and, once the city is big enough, a loop around the quarters."""

    stops = _stops(shapes, network, placements)
    if len(stops) < 2:
        return (stops, {}, {"stops": len(stops), "lines": 0})

    lines: dict[str, TransitLine] = {}
    routes = _routes(stops)

    for index, (name, ordered) in enumerate(routes):
        points: list[Vec2] = []
        used: list[str] = []
        for step in range(len(ordered) - 1):
            leg = transit_path(network, stops[ordered[step]].node_id, stops[ordered[step + 1]].node_id)
            if not leg:
                continue
            legs = path_points(network, leg)
            points.extend(legs if not points else legs[1:])
            if ordered[step] not in used:
                used.append(ordered[step])
            used.append(ordered[step + 1])
        if len(points) < 2:
            continue
        line_id = f"line_{index + 1}"
        lines[line_id] = TransitLine(
            line_id=line_id,
            name=name,
            stop_ids=used,
            path=[g.round_point(p) for p in points],
            colour=LINE_COLOURS[index % len(LINE_COLOURS)],
        )

    report = {
        "stops": len(stops),
        "lines": len(lines),
        "line_km": round(sum(g.polyline_length(l.path) for l in lines.values()) / 1000.0, 2),
    }
    return (stops, lines, report)


def _stops(
    shapes: dict[str, DistrictShape],
    network: StreetNetwork,
    placements: dict[str, BuildingPlacement],
) -> dict[str, TransitStop]:
    """One stop at each quarter's heart, plus one at every transport hub."""

    stops: dict[str, TransitStop] = {}
    for district_id in sorted(shapes):
        shape = shapes[district_id]
        centre = g.centroid(shape.built_polygon) if len(shape.built_polygon) >= 3 else shape.centre
        node = _nearest_node(network, centre, district_id)
        if not node:
            continue
        stops[f"stop_{district_id}"] = TransitStop(
            stop_id=f"stop_{district_id}",
            point=network.nodes[node].point,
            district_id=district_id,
            node_id=node,
            name=f"{shape.name} Centre".strip(),
        )
    for building_id in sorted(placements):
        placement = placements[building_id]
        if placement.kind != "transport_hub" or not placement.access_node:
            continue
        stops[f"stop_{building_id}"] = TransitStop(
            stop_id=f"stop_{building_id}",
            point=network.nodes[placement.access_node].point,
            district_id=placement.district_id,
            node_id=placement.access_node,
            name=placement.address or "Interchange",
        )
    return stops


def _routes(stops: dict[str, TransitStop]) -> list[tuple[str, list[str]]]:
    """Order the stops three ways: west-east, north-south, and around the ring."""

    ids = sorted(stops)
    centre = (
        sum(stops[s].point[0] for s in ids) / len(ids),
        sum(stops[s].point[1] for s in ids) / len(ids),
    )
    east_west = sorted(ids, key=lambda s: (stops[s].point[0], s))
    north_south = sorted(ids, key=lambda s: (stops[s].point[1], s))
    routes = [("Cross-City West", east_west), ("Cross-City North", north_south)]
    if len(ids) >= 6:
        ring = sorted(
            ids, key=lambda s: (math.atan2(stops[s].point[1] - centre[1], stops[s].point[0] - centre[0]), s)
        )
        routes.append(("Quarter Loop", ring + [ring[0]]))
    return routes


def _nearest_node(network: StreetNetwork, point: Vec2, district_id: str = "") -> str:
    best: tuple[float, str] | None = None
    for node_id in sorted(network.nodes):
        node = network.nodes[node_id]
        if district_id and node.district_id != district_id:
            continue
        d = g.distance(node.point, point)
        if best is None or d < best[0]:
            best = (d, node_id)
    if best is None and district_id:
        return _nearest_node(network, point)
    return best[1] if best else ""
