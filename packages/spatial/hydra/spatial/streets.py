"""Stage 2 -- the street graph.

Two kinds of road, built in this order because the big ones decide where the small ones can
go:

*Arterials* link the built quarters to each other and run out to the city edge. They come
from a minimum spanning tree over the quarter centres, plus a few extra edges so the network
has loops rather than being a tree an accident could cut in half.

*Local streets* are a lattice laid at the district's own grid angle and clipped to its built
polygon. Lattice nodes falling inside an arterial's right-of-way are removed, which is what
gives the arterial a corridor instead of letting it run straight through people's blocks.
Every k-th lattice line is promoted to a collector, so districts get spines.

The result is planar by construction: lattice nodes only ever connect to their immediate
neighbours, and arterials meet the lattice at explicit junction nodes. Nothing crosses
without a node, so the graph can be walked for routing.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

from hydra.kernel.rng import DeterministicRng, derive_seed

from . import geometry as g
from .model import (
    DistrictShape,
    Lattice,
    StreetClass,
    StreetNetwork,
    StreetNode,
    StreetSegment,
    Vec2,
)
from .naming import NamePool, NameRegistry

ARTERIAL_WIDTH_M = 22.0
COLLECTOR_WIDTH_M = 13.0
LOCAL_WIDTH_M = 8.0

#: Every n-th lattice line becomes a collector.
COLLECTOR_EVERY = 4
#: Extra arterial edges beyond the spanning tree, as a fraction of the tree size.
LOOP_RATIO = 0.45
#: Right-of-way half width, as a multiple of the arterial's own width.
CORRIDOR_FACTOR = 1.6
#: An arterial junction links to lattice nodes within this multiple of the block size.
JUNCTION_REACH = 0.85
#: How far inside a quarter's built edge an arterial terminates.
EDGE_STANDOFF_M = 40.0
#: How far short of the city boundary a gate road stops.
GATE_STANDOFF_M = 60.0


def build_streets(
    seed: int,
    boundary: Sequence[Vec2],
    shapes: dict[str, DistrictShape],
    names: NameRegistry | None = None,
) -> tuple[StreetNetwork, dict[str, Lattice], dict[str, object]]:
    network = StreetNetwork()
    rng = DeterministicRng(derive_seed(seed, "spatial", "streets"))
    registry = names if names is not None else NameRegistry()

    arterials = _arterial_paths(rng, boundary, shapes)
    _lay_arterials(network, arterials, shapes, seed, registry)
    corridors = [(path, ARTERIAL_WIDTH_M * CORRIDOR_FACTOR) for path in arterials]

    lattices: dict[str, Lattice] = {}
    for district_id in sorted(shapes):
        lattices[district_id] = _lay_district_grid(network, shapes[district_id], corridors, registry)

    junctions = _join_arterials_to_grid(network, shapes)
    stitched = _stitch_components(network)

    report = {
        "nodes": len(network.nodes),
        "segments": len(network.segments),
        "arterials": sum(1 for s in network.segments.values() if s.klass is StreetClass.ARTERIAL),
        "collectors": sum(1 for s in network.segments.values() if s.klass is StreetClass.COLLECTOR),
        "local": sum(1 for s in network.segments.values() if s.klass is StreetClass.LOCAL),
        "junctions": junctions,
        "stitched": stitched,
        "components": len(connected_components(network)),
        "length_km": round(sum(s.length_m for s in network.segments.values()) / 1000.0, 2),
    }
    return (network, lattices, report)


# -- arterials --------------------------------------------------------------------


def _arterial_paths(
    rng: DeterministicRng, boundary: Sequence[Vec2], shapes: dict[str, DistrictShape]
) -> list[list[Vec2]]:
    """Spanning tree over quarter centres, plus loops, plus roads out of the city."""

    ids = sorted(shapes)
    hubs = {d: _built_centre(shapes[d]) for d in ids}
    if len(ids) < 2:
        return []

    edges = _spanning_tree(ids, hubs)
    edges += _loop_edges(ids, hubs, edges)

    paths = []
    for a, b in edges:
        start = _edge_of(shapes[a], hubs[a], hubs[b])
        end = _edge_of(shapes[b], hubs[b], hubs[a])
        paths.append(_bend(rng, start, end))
    paths += _gate_roads(rng, boundary, hubs, shapes)
    return paths


def _edge_of(shape: DistrictShape, hub: Vec2, toward: Vec2) -> Vec2:
    """Where the road meets this quarter: its built edge, not its middle.

    An arterial aimed at a centroid drives a right-of-way straight through the densest part
    of a district and deletes the blocks it was supposed to serve. Real trunk roads skirt
    quarters and hand off to the local streets at the edge, which is what this does.
    """

    built = shape.built_polygon
    direction = g.normalise(g.sub(toward, hub))
    if len(built) < 3 or g.length(direction) < g.EPS:
        return hub
    crossing = _ray_hit(built, hub, direction)
    if crossing is None:
        return hub
    # Stop a touch inside so the junction has lattice to attach to.
    return g.add(crossing, g.scale(direction, -EDGE_STANDOFF_M))


def _spanning_tree(ids: Sequence[str], hubs: dict[str, Vec2]) -> list[tuple[str, str]]:
    """Prim's algorithm, started at the most central hub so the trunk radiates outward."""

    centre = (
        sum(hubs[i][0] for i in ids) / len(ids),
        sum(hubs[i][1] for i in ids) / len(ids),
    )
    start = min(ids, key=lambda i: (g.distance(hubs[i], centre), i))
    inside = {start}
    edges: list[tuple[str, str]] = []
    while len(inside) < len(ids):
        best: tuple[float, str, str] | None = None
        for a in sorted(inside):
            for b in ids:
                if b in inside:
                    continue
                d = g.distance(hubs[a], hubs[b])
                if best is None or (d, a, b) < best:
                    best = (d, a, b)
        assert best is not None
        edges.append((best[1], best[2]))
        inside.add(best[2])
    return edges


def _loop_edges(
    ids: Sequence[str], hubs: dict[str, Vec2], tree: Sequence[tuple[str, str]]
) -> list[tuple[str, str]]:
    """Shortest non-tree links, so the network is not a single point of failure."""

    have = {frozenset(e) for e in tree}
    candidates = []
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            if frozenset((a, b)) in have:
                continue
            candidates.append((g.distance(hubs[a], hubs[b]), a, b))
    candidates.sort()
    wanted = int(len(tree) * LOOP_RATIO)
    return [(a, b) for _, a, b in candidates[:wanted]]


def _bend(rng: DeterministicRng, a: Vec2, b: Vec2) -> list[Vec2]:
    """One gentle dogleg. Perfectly straight inter-district roads look drawn, not built."""

    mid = g.lerp(a, b, rng.uniform(0.42, 0.58))
    normal = g.perpendicular(g.normalise(g.sub(b, a)))
    offset = g.distance(a, b) * rng.uniform(-0.10, 0.10)
    return [a, g.add(mid, g.scale(normal, offset)), b]


def _gate_roads(
    rng: DeterministicRng,
    boundary: Sequence[Vec2],
    hubs: dict[str, Vec2],
    shapes: dict[str, DistrictShape],
) -> list[list[Vec2]]:
    """From the outermost quarters, carry on to the city limit."""

    if not boundary:
        return []
    centre = g.centroid(boundary)
    outer = sorted(hubs, key=lambda k: (-g.distance(hubs[k], centre), k))[: max(2, len(hubs) // 3)]

    roads = []
    for district_id in outer:
        hub = hubs[district_id]
        direction = g.normalise(g.sub(hub, centre))
        if g.length(direction) < g.EPS:
            continue
        limit = _ray_hit(boundary, hub, direction)
        if limit is None:
            continue
        exit_point = g.add(limit, g.scale(direction, -GATE_STANDOFF_M))
        start = _edge_of(shapes[district_id], hub, exit_point)
        if g.distance(start, exit_point) < GATE_STANDOFF_M:
            continue
        roads.append(_bend(rng, start, exit_point))
    return roads


def _ray_hit(poly: Sequence[Vec2], origin: Vec2, direction: Vec2) -> Vec2 | None:
    """Nearest forward crossing of a closed ring by a ray."""

    best_t: float | None = None
    best_point: Vec2 | None = None
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        edge = g.sub(b, a)
        denom = g.cross(direction, edge)
        if abs(denom) < g.EPS:
            continue
        diff = g.sub(a, origin)
        t = g.cross(diff, edge) / denom
        u = g.cross(diff, direction) / denom
        if t > g.EPS and 0.0 <= u <= 1.0 and (best_t is None or t < best_t):
            best_t = t
            best_point = g.add(origin, g.scale(direction, t))
    return best_point


def _lay_arterials(
    network: StreetNetwork,
    paths: Sequence[Sequence[Vec2]],
    shapes: dict[str, DistrictShape],
    seed: int,
    registry: NameRegistry,
) -> None:
    pool = registry.pool(derive_seed(seed, "spatial", "arterials"), "commercial")
    for index, path in enumerate(paths):
        name = pool.street("arterial", index)
        previous = ""
        for step, point in enumerate(path):
            node_id = f"a{index}_{step}"
            network.add_node(StreetNode(node_id, g.round_point(point), _district_at(shapes, point)))
            if previous:
                _connect(network, previous, node_id, StreetClass.ARTERIAL, ARTERIAL_WIDTH_M, name)
            previous = node_id


# -- district lattices ------------------------------------------------------------


def _lay_district_grid(
    network: StreetNetwork,
    shape: DistrictShape,
    corridors: Sequence[tuple[Sequence[Vec2], float]],
    registry: NameRegistry,
) -> Lattice:
    angle = shape.grid_angle
    spacing = shape.block_size_m
    built = shape.built_polygon
    lattice = Lattice(shape.district_id, angle, spacing, 0.0, 0.0)
    if len(built) < 3:
        return lattice

    pool = registry.pool(shape.seed, shape.kind)

    # Work in the district's own frame, where the lattice is axis aligned.
    rotated = [g.rotate(p, -angle) for p in built]
    min_u, min_v, max_u, max_v = g.bbox(rotated)
    cols = max(2, int(math.ceil((max_u - min_u) / spacing)) + 1)
    rows = max(2, int(math.ceil((max_v - min_v) / spacing)) + 1)
    # Centre the lattice on the polygon so the fabric is not lopsided.
    lattice.origin_u = min_u - ((cols - 1) * spacing - (max_u - min_u)) * 0.5
    lattice.origin_v = min_v - ((rows - 1) * spacing - (max_v - min_v)) * 0.5

    for i in range(cols):
        for j in range(rows):
            point = g.rotate((lattice.origin_u + i * spacing, lattice.origin_v + j * spacing), angle)
            if not g.contains(built, point):
                continue
            if _in_corridor(point, corridors):
                continue
            node_id = f"g_{shape.district_id}_{i}_{j}"
            network.add_node(StreetNode(node_id, g.round_point(point), shape.district_id))
            lattice.nodes[(i, j)] = node_id

    for i in range(cols):
        klass = _klass_of(i)
        lattice.column_width[i] = _width_of(klass)
        lattice.column_name[i] = pool.street(klass.value, i)
    for j in range(rows):
        klass = _klass_of(j)
        lattice.row_width[j] = _width_of(klass)
        lattice.row_name[j] = pool.street(klass.value, cols + j)

    for (i, j), node_id in sorted(lattice.nodes.items()):
        right = lattice.nodes.get((i + 1, j))
        if right:
            klass = _klass_of(j)
            segment = _connect(
                network, node_id, right, klass, _width_of(klass), lattice.row_name[j], shape.district_id
            )
            if segment:
                lattice.row_segment[(i, j)] = segment
        up = lattice.nodes.get((i, j + 1))
        if up:
            klass = _klass_of(i)
            segment = _connect(
                network, node_id, up, klass, _width_of(klass), lattice.column_name[i], shape.district_id
            )
            if segment:
                lattice.column_segment[(i, j)] = segment
    return lattice


def _klass_of(line_index: int) -> StreetClass:
    return StreetClass.COLLECTOR if line_index % COLLECTOR_EVERY == 0 else StreetClass.LOCAL


def _width_of(klass: StreetClass) -> float:
    if klass is StreetClass.ARTERIAL:
        return ARTERIAL_WIDTH_M
    return COLLECTOR_WIDTH_M if klass is StreetClass.COLLECTOR else LOCAL_WIDTH_M


def _in_corridor(point: Vec2, corridors: Sequence[tuple[Sequence[Vec2], float]]) -> bool:
    for path, half_width in corridors:
        for i in range(len(path) - 1):
            if g.point_segment_distance(point, path[i], path[i + 1]) < half_width:
                return True
    return False


# -- stitching --------------------------------------------------------------------


def _join_arterials_to_grid(network: StreetNetwork, shapes: dict[str, DistrictShape]) -> int:
    """Link every arterial node to the lattice it passes, so the graph is walkable."""

    lattice: dict[str, list[str]] = {}
    for node in network.nodes.values():
        if node.node_id.startswith("g_"):
            lattice.setdefault(node.district_id, []).append(node.node_id)

    joined = 0
    for node_id in sorted(n for n in network.nodes if n.startswith("a")):
        node = network.nodes[node_id]
        candidates = lattice.get(node.district_id) or []
        if not candidates:
            continue
        reach = JUNCTION_REACH * shapes[node.district_id].block_size_m + ARTERIAL_WIDTH_M * CORRIDOR_FACTOR
        near = sorted(
            (g.distance(network.nodes[c].point, node.point), c) for c in candidates
        )[:2]
        for distance, candidate in near:
            if distance > reach:
                continue
            _connect(network, node_id, candidate, StreetClass.COLLECTOR, COLLECTOR_WIDTH_M,
                     "", node.district_id)
            joined += 1
    return joined


def _stitch_components(network: StreetNetwork) -> int:
    """Join every stranded fragment to the main network by its shortest link.

    Corridors and polygon edges inevitably cut a few lattice nodes loose. Leaving them
    isolated would mean buildings the routing graph cannot reach, so each fragment gets one
    service road to the nearest node of the largest component -- the smallest honest fix.
    """

    added = 0
    while True:
        groups = connected_components(network)
        if len(groups) < 2:
            return added
        groups.sort(key=lambda group: (-len(group), min(group)))
        main = groups[0]
        best: tuple[float, str, str] | None = None
        for group in groups[1:]:
            for node_id in sorted(group):
                point = network.nodes[node_id].point
                for other in sorted(main):
                    d = g.distance(point, network.nodes[other].point)
                    if best is None or (d, node_id, other) < best:
                        best = (d, node_id, other)
        if best is None:
            return added
        _connect(network, best[1], best[2], StreetClass.LOCAL, LOCAL_WIDTH_M,
                 "", network.nodes[best[1]].district_id)
        added += 1


def _connect(
    network: StreetNetwork,
    a: str,
    b: str,
    klass: StreetClass,
    width: float,
    name: str = "",
    district_id: str = "",
) -> str:
    segment_id = f"s_{a}__{b}"
    if segment_id in network.segments:
        return segment_id
    if f"s_{b}__{a}" in network.segments:
        return f"s_{b}__{a}"
    length = g.distance(network.nodes[a].point, network.nodes[b].point)
    network.add_segment(
        StreetSegment(
            segment_id=segment_id,
            a=a,
            b=b,
            klass=klass,
            width_m=width,
            length_m=round(length, 2),
            district_id=district_id,
            name=name,
        )
    )
    return segment_id


def _built_centre(shape: DistrictShape) -> Vec2:
    return g.centroid(shape.built_polygon) if len(shape.built_polygon) >= 3 else shape.centre


def _district_at(shapes: dict[str, DistrictShape], point: Vec2) -> str:
    for district_id in sorted(shapes):
        if g.contains(shapes[district_id].polygon, point):
            return district_id
    return ""


def connected_components(network: StreetNetwork) -> list[set[str]]:
    """Used by tests and diagnostics: the street graph should be one piece."""

    seen: set[str] = set()
    groups: list[set[str]] = []
    for start in sorted(network.nodes):
        if start in seen:
            continue
        stack = [start]
        group: set[str] = set()
        while stack:
            current = stack.pop()
            if current in group:
                continue
            group.add(current)
            for neighbour, _, _ in network.adjacency.get(current, ()):
                if neighbour not in group:
                    stack.append(neighbour)
        seen |= group
        groups.append(group)
    return groups
