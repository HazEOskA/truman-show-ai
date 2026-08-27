"""Stage 1 -- territory.

Turns eight districts with an ``area_km2`` and a rough relative position into eight
non-overlapping polygons that tile a city boundary and hit their target areas.

The method is a *power diagram* (a weighted Voronoi diagram) whose weights are fitted by
iteration until every cell's area matches the district's declared area. That gives cells
which are convex, gapless and exact to a fraction of a percent, from nothing but the seed
positions genesis already chose -- so the projection honours the arrangement the world was
built with instead of inventing a new one.

Inside each cell sits a smaller *built* polygon. Hydra's districts are municipal areas of
several km² holding a few dozen buildings each; the settlement is a dense core within that,
and the rest is open land. The built polygon is anchored at the point nearest the city
centre, which arranges the quarters radially around the middle instead of scattering them.
"""

from __future__ import annotations

import math
from typing import Sequence

from hydra.kernel.rng import DeterministicRng, derive_seed

from . import geometry as g
from .model import DistrictShape, Vec2
from .source import CityInput
from .zoning import MAX_BLOCK_M, MIN_BLOCK_M, open_ratio, parcels_per_block, plot_area

BOUNDARY_SAMPLES = 128
BOUNDARY_VERTICES = 72
FIT_ITERATIONS = 240
FIT_GAIN = 0.85
#: Seeds are packed into this fraction of the boundary radius so no cell is pinched.
SEED_FILL = 0.58
#: A district never builds on more than this share of its own land.
MAX_BUILT_FRACTION = 0.85
#: Slack on the built footprint: quarters are not discs, and arterials eat into them.
EDGE_ALLOWANCE = 1.18


def build_territory(city: CityInput) -> tuple[list[Vec2], dict[str, DistrictShape], dict[str, object]]:
    """Return ``(boundary, shapes, report)`` in metres."""

    districts = list(city.districts)
    if not districts:
        return ([], {}, {"districts": 0})

    total_area = sum(d.area_km2 for d in districts) * 1e6
    rng = DeterministicRng(derive_seed(city.seed, "spatial", "territory", city.city_id))

    sites = _seed_points(districts)
    aspect = _aspect_of(sites)
    boundary = _boundary(rng, total_area, aspect)
    sites = _fit_sites_inside(sites, boundary)

    order = [d.district_id for d in districts]
    targets = [d.area_km2 * 1e6 for d in districts]
    points = [sites[d] for d in order]
    cells, fit = _fit_power_diagram(boundary, points, targets)

    city_centre = g.centroid(boundary)
    shapes: dict[str, DistrictShape] = {}
    for district, cell in zip(districts, cells):
        if len(cell) < 3:
            cell = list(boundary)
        cell = g.ensure_ccw(g.simplify(cell, 4.0))
        cell_area = g.area(cell)
        centre = g.centroid(cell)
        seed = derive_seed(city.seed, "spatial", "district", district.district_id)
        block_size = _block_size(city, district.district_id, district.kind)
        built_area = _built_area(city, district.district_id, district.kind, block_size)
        built_area = min(built_area, cell_area * MAX_BUILT_FRACTION)
        built = _built_polygon(cell, city_centre, built_area)
        shapes[district.district_id] = DistrictShape(
            district_id=district.district_id,
            name=district.name,
            kind=district.kind,
            polygon=[g.round_point(p) for p in cell],
            centre=g.round_point(centre),
            area_m2=round(cell_area, 2),
            built_polygon=[g.round_point(p) for p in built],
            built_area_m2=round(g.area(built), 2),
            grid_angle=_grid_angle(seed, centre, city_centre),
            block_size_m=block_size,
            seed=seed,
        )

    report = {
        "districts": len(shapes),
        "boundary_area_m2": round(g.area(boundary), 2),
        "target_area_m2": round(total_area, 2),
        "area_fit_max_error": fit["max_error"],
        "area_fit_iterations": fit["iterations"],
        "built_area_m2": round(sum(s.built_area_m2 for s in shapes.values()), 2),
    }
    report["built_fraction"] = round(float(report["built_area_m2"]) / max(1.0, total_area), 4)
    return ([g.round_point(p) for p in boundary], shapes, report)


# -- boundary ---------------------------------------------------------------------


def _boundary(rng: DeterministicRng, target_area: float, aspect: float) -> list[Vec2]:
    """An organic closed shape of exactly ``target_area``, elongated like the seed spread."""

    harmonics = [(k, rng.uniform(0.05, 0.17) / (k - 1), rng.uniform(0.0, math.tau)) for k in (2, 3, 5, 7)]
    raw: list[Vec2] = []
    for i in range(BOUNDARY_SAMPLES):
        theta = math.tau * i / BOUNDARY_SAMPLES
        r = 1.0
        for k, amp, phase in harmonics:
            r += amp * math.sin(k * theta + phase)
        r = max(0.45, r)
        raw.append((r * math.cos(theta) * aspect, r * math.sin(theta) / aspect))
    scale = math.sqrt(target_area / max(g.EPS, g.area(raw)))
    scaled = [g.scale(p, scale) for p in raw]
    return g.ensure_ccw(g.resample(scaled, BOUNDARY_VERTICES))


def _aspect_of(sites: dict[str, Vec2]) -> float:
    """Square root of the seed spread's aspect ratio, clamped to something city-shaped."""

    if len(sites) < 2:
        return 1.0
    min_x, min_y, max_x, max_y = g.bbox(sites.values())
    width = max(1.0, max_x - min_x)
    height = max(1.0, max_y - min_y)
    return max(0.78, min(1.28, math.sqrt(width / height)))


# -- sites ------------------------------------------------------------------------


def _seed_points(districts: Sequence) -> dict[str, Vec2]:
    """District hints in metres, or a deterministic ring when genesis gave none."""

    points = {d.district_id: (d.hint_x * 1000.0, d.hint_y * 1000.0) for d in districts}
    distinct = {g.round_point(p, 1) for p in points.values()}
    if len(distinct) >= max(2, len(points) - 1):
        return points
    # Degenerate hints: fall back to a ring, largest district outermost, order by id.
    ordered = sorted(districts, key=lambda d: d.district_id)
    ring: dict[str, Vec2] = {}
    for i, d in enumerate(ordered):
        theta = math.tau * i / len(ordered)
        radius = 1000.0 * math.sqrt(sum(x.area_km2 for x in ordered))
        ring[d.district_id] = (radius * math.cos(theta), radius * math.sin(theta))
    return ring


def _fit_sites_inside(sites: dict[str, Vec2], boundary: Sequence[Vec2]) -> dict[str, Vec2]:
    """Centre the seed arrangement on the boundary and shrink it to fit comfortably."""

    if not sites:
        return {}
    centre = g.centroid(boundary)
    keys = sorted(sites)
    mean = (
        sum(sites[k][0] for k in keys) / len(keys),
        sum(sites[k][1] for k in keys) / len(keys),
    )
    reach = max(g.distance(sites[k], mean) for k in keys)
    limit = min(g.distance(p, centre) for p in boundary) * SEED_FILL
    factor = 1.0 if reach < g.EPS else min(1.0, limit / reach)
    return {k: g.add(centre, g.scale(g.sub(sites[k], mean), factor)) for k in keys}


# -- power diagram ----------------------------------------------------------------


def power_cells(
    boundary: Sequence[Vec2], sites: Sequence[Vec2], weights: Sequence[float]
) -> list[list[Vec2]]:
    """Clip ``boundary`` into one convex cell per site under the power distance."""

    cells: list[list[Vec2]] = []
    for i, s in enumerate(sites):
        poly = list(boundary)
        for j, t in enumerate(sites):
            if i == j:
                continue
            normal = g.sub(t, s)
            offset = (g.dot(t, t) - g.dot(s, s) - weights[j] + weights[i]) * 0.5
            poly = g.clip_halfplane(poly, normal, offset)
            if len(poly) < 3:
                poly = []
                break
        cells.append(poly)
    return cells


def _fit_power_diagram(
    boundary: Sequence[Vec2], sites: Sequence[Vec2], targets: Sequence[float]
) -> tuple[list[list[Vec2]], dict[str, object]]:
    """Iterate the weights until each cell's area matches its target."""

    n = len(sites)
    weights = [0.0] * n
    total = sum(targets) or 1.0
    span = _mean_square_distance(sites) or 1.0
    cells = power_cells(boundary, sites, weights)
    best_error = float("inf")
    best_cells = cells
    iterations = 0

    for step in range(FIT_ITERATIONS):
        iterations = step + 1
        areas = [g.area(c) if len(c) >= 3 else 0.0 for c in cells]
        errors = [(targets[i] - areas[i]) / targets[i] for i in range(n)]
        worst = max(abs(e) for e in errors)
        if worst < best_error:
            best_error, best_cells = worst, cells
        if worst < 0.002:
            break
        for i in range(n):
            if areas[i] <= 0.0:
                weights[i] += 0.18 * span          # starved cell: buy it back in
                continue
            delta = FIT_GAIN * span * (targets[i] - areas[i]) / total
            weights[i] += max(-0.25 * span, min(0.25 * span, delta))
        mean_w = sum(weights) / n
        weights = [w - mean_w for w in weights]     # weights are gauge-free
        cells = power_cells(boundary, sites, weights)

    areas = [g.area(c) if len(c) >= 3 else 0.0 for c in cells]
    final = max(abs((targets[i] - areas[i]) / targets[i]) for i in range(n))
    if final <= best_error:
        best_cells, best_error = cells, final
    return (best_cells, {"max_error": round(best_error, 5), "iterations": iterations})


def _mean_square_distance(sites: Sequence[Vec2]) -> float:
    if len(sites) < 2:
        return 0.0
    total = 0.0
    count = 0
    for i in range(len(sites)):
        for j in range(i + 1, len(sites)):
            d = g.sub(sites[i], sites[j])
            total += g.dot(d, d)
            count += 1
    return total / count


# -- built fabric -----------------------------------------------------------------


def _built_area(city: CityInput, district_id: str, district_kind: str, block_size_m: float) -> float:
    """How much land this district needs, counted in whole street blocks.

    Sizing by plot area alone undercounts badly: a lattice only yields complete blocks in
    its interior, and a small quarter is nearly all edge. Inverting the disc formula --
    ``blocks ~ pi (R/s - 1)^2`` -- prices that perimeter loss in directly, which is the
    difference between a district that can house its buildings and one that cannot.
    """

    buildings = city.buildings_in(district_id)
    if not buildings:
        return 0.0
    parcels_needed = len(buildings) / max(0.1, 1.0 - open_ratio(district_kind))
    blocks_needed = max(1.0, parcels_needed / parcels_per_block(district_kind))
    radius = block_size_m * (1.0 + math.sqrt(blocks_needed / math.pi))
    return math.pi * radius * radius * EDGE_ALLOWANCE


def _built_polygon(cell: Sequence[Vec2], city_centre: Vec2, built_area: float) -> list[Vec2]:
    """Shrink the cell toward its point nearest the city centre.

    Anchoring cityward rather than at the centroid is what makes the quarters face each
    other: every district's fabric grows from its inner edge, so the settlements line up
    around the middle instead of drifting apart.
    """

    cell_area = g.area(cell)
    if built_area <= 0.0 or cell_area <= 0.0:
        return []
    factor = min(1.0, math.sqrt(built_area / cell_area))
    anchor = _anchor(cell, city_centre)
    inner = [g.add(anchor, g.scale(g.sub(p, anchor), factor)) for p in cell]
    return g.ensure_ccw(inner)


def _anchor(cell: Sequence[Vec2], city_centre: Vec2) -> Vec2:
    """The city centre if the cell holds it, otherwise the cell point closest to it."""

    if g.contains(cell, city_centre):
        return city_centre
    best = cell[0]
    best_d = float("inf")
    n = len(cell)
    for i in range(n):
        a, b = cell[i], cell[(i + 1) % n]
        ab = g.sub(b, a)
        denom = g.dot(ab, ab)
        t = 0.0 if denom < g.EPS else max(0.0, min(1.0, g.dot(g.sub(city_centre, a), ab) / denom))
        p = g.add(a, g.scale(ab, t))
        d = g.distance(p, city_centre)
        if d < best_d:
            best_d, best = d, p
    # Pull just inside the edge so the fabric sits on land, not on the boundary line.
    inward = g.normalise(g.sub(g.centroid(cell), best))
    return g.add(best, g.scale(inward, 1.0))


def _grid_angle(seed: int, centre: Vec2, city_centre: Vec2) -> float:
    """Streets run toward the city centre, with a per-district twist."""

    rng = DeterministicRng(derive_seed(seed, "grid"))
    radial = g.sub(centre, city_centre)
    base = math.atan2(radial[1], radial[0]) if g.length(radial) > 1.0 else rng.uniform(0.0, math.tau)
    return round((base + rng.uniform(-0.38, 0.38)) % (math.pi * 0.5), 6)


def _block_size(city: CityInput, district_id: str, district_kind: str) -> float:
    buildings = city.buildings_in(district_id)
    if not buildings:
        return MIN_BLOCK_M
    mean_plot = sum(plot_area(b.kind) for b in buildings) / len(buildings)
    block_area = mean_plot * parcels_per_block(district_kind)
    return round(max(MIN_BLOCK_M, min(MAX_BLOCK_M, math.sqrt(block_area))), 2)
