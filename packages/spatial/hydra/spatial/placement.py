"""Stage 4 -- putting the city's buildings on the ground.

Every building in world state gets exactly one parcel. Nothing is invented: if a district
has more plots than buildings -- and it always does, because cities have parks -- the
leftovers become open space, not filler structures. If the projection ever cannot place a
building it says so in the report rather than dropping it quietly.

Matching is a greedy assignment on a score, biggest buildings first, because a power plant
that misses its plot has nowhere else to go while a flat can sit almost anywhere. The score
weighs three things a real planner would: how well the plot fits the footprint, whether the
kind wants a main street or the district edge, and how far it is from the quarter's centre.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from hydra.kernel.rng import DeterministicRng, derive_seed

from . import geometry as g
from .model import (
    BuildingPlacement,
    DistrictShape,
    LandUse,
    OpenSpace,
    Parcel,
    StreetClass,
    StreetNetwork,
    Vec2,
)
from .naming import NameRegistry, house_number
from .source import BuildingInput, CityInput
from .zoning import footprint_for, plot_area, zoning_for

#: Gap between a footprint and its plot boundary.
SETBACK_M = 3.0
#: Open ground next to industry is a yard; next to housing it is a park.
YARD_KINDS = ("industrial", "port")


def build_placements(
    city: CityInput,
    shapes: dict[str, DistrictShape],
    parcels: dict[str, Parcel],
    network: StreetNetwork,
    names: NameRegistry | None = None,
) -> tuple[dict[str, BuildingPlacement], dict[str, OpenSpace], dict[str, object]]:
    placements: dict[str, BuildingPlacement] = {}
    spaces: dict[str, OpenSpace] = {}
    unplaced: list[str] = []
    registry = names if names is not None else NameRegistry()

    by_district: dict[str, list[Parcel]] = {}
    for parcel in parcels.values():
        by_district.setdefault(parcel.district_id, []).append(parcel)

    arterial_points = _major_street_points(network)

    for district_id in sorted(shapes):
        shape = shapes[district_id]
        available = sorted(by_district.get(district_id, []), key=lambda p: p.parcel_id)
        buildings = sorted(
            city.buildings_in(district_id),
            key=lambda b: (-plot_area(b.kind), b.building_id),
        )
        taken, missed = _assign(shape, buildings, available, arterial_points, placements, network)
        unplaced.extend(missed)
        _open_ground(shape, [p for p in available if p.parcel_id not in taken], spaces, registry)

    report = {
        "placed": len(placements),
        "unplaced": len(unplaced),
        "unplaced_ids": sorted(unplaced)[:20],
        "open_spaces": len(spaces),
        "occupancy": round(len(placements) / max(1, len(parcels)), 4),
    }
    return (placements, spaces, report)


# -- assignment -------------------------------------------------------------------


@dataclass(slots=True)
class _Site:
    """Everything about a plot that does not depend on which building lands on it.

    Computed once per parcel. Scoring inside the assignment loop is otherwise quadratic in
    parcels times buildings times arterial samples, which for Hydra is a hundred million
    distance calls for a layout that has to be free.
    """

    parcel: Parcel
    area_m2: float
    outward: float          # 0 at the quarter's heart, 1.5 at its rim
    frontage: float         # 1 on a main street, 0 far from one


def _sites(
    shape: DistrictShape, parcels: Sequence[Parcel], arterial_points: Sequence[Vec2]
) -> dict[str, _Site]:
    reach = max(1.0, math.sqrt(max(1.0, shape.built_area_m2) / math.pi))
    sites: dict[str, _Site] = {}
    for parcel in parcels:
        outward = min(1.5, g.distance(parcel.centre, shape.centre) / reach)
        frontage = 0.0
        if arterial_points:
            nearest = min(g.distance(parcel.centre, p) for p in arterial_points)
            frontage = max(0.0, 1.0 - nearest / (reach * 1.2))
        sites[parcel.parcel_id] = _Site(parcel, parcel.area_m2, outward, frontage)
    return sites


def _assign(
    shape: DistrictShape,
    buildings: Sequence[BuildingInput],
    parcels: Sequence[Parcel],
    arterial_points: Sequence[Vec2],
    placements: dict[str, BuildingPlacement],
    network: StreetNetwork,
) -> tuple[set[str], list[str]]:
    free = _sites(shape, parcels, arterial_points)
    rng = DeterministicRng(derive_seed(shape.seed, "placement"))
    taken: set[str] = set()
    missed: list[str] = []
    numbering: dict[str, int] = {}

    for building in buildings:
        best_id = _best_parcel(building, free)
        if best_id is None:
            missed.append(building.building_id)
            continue
        site = free.pop(best_id)
        taken.add(best_id)
        placements[building.building_id] = _place(
            building, site.parcel, shape, rng, numbering, network
        )
    return (taken, missed)


def _best_parcel(building: BuildingInput, free: dict[str, _Site]) -> str | None:
    if not free:
        return None
    want = max(1.0, plot_area(building.kind))
    z = zoning_for(building.kind)
    best: tuple[float, str] | None = None
    for parcel_id in sorted(free):
        score = _score(free[parcel_id], want, z)
        if best is None or score > best[0]:
            best = (score, parcel_id)
    return best[1] if best else None


def _score(site: _Site, want: float, z) -> float:
    """Higher is better. Size fit dominates; siting preferences break the ties."""

    ratio = site.area_m2 / want
    # A plot that is too small hurts far more than one that is too big.
    fit = ratio if ratio < 1.0 else 1.0 / (1.0 + (ratio - 1.0) * 0.35)
    return fit * 2.0 + site.frontage * z.frontage_pull + site.outward * (z.edge_pull - 0.15)


def _place(
    building: BuildingInput,
    parcel: Parcel,
    shape: DistrictShape,
    rng: DeterministicRng,
    numbering: dict[str, int],
    network: StreetNetwork,
) -> BuildingPlacement:
    width, depth, floors, height = footprint_for(building.kind, building.capacity)

    # ``frontage_angle`` is the plot's outward normal, so the building's frame is turned a
    # quarter turn from it: width runs *along* the street, depth runs back into the block.
    # Getting this the wrong way round puts the long side of a terrace across the pavement.
    facing = parcel.frontage_angle
    angle = (facing + math.pi * 0.5) % math.tau
    plot_width, plot_depth = g.oriented_extent(parcel.polygon, angle)
    width = min(width, max(4.0, plot_width - SETBACK_M * 2.0))
    depth = min(depth, max(4.0, plot_depth - SETBACK_M * 2.0))

    # Sit toward the street rather than in the middle of the plot: gardens go behind.
    to_street = (math.cos(facing), math.sin(facing))
    shift = max(0.0, (plot_depth - depth) * 0.5 - SETBACK_M)
    centre = g.add(parcel.centre, g.scale(to_street, shift))
    footprint = g.rectangle(centre, width, depth, angle)
    entrance = g.add(centre, g.scale(to_street, depth * 0.5 + 1.5))

    ordinal = numbering.get(parcel.street_name, 0)
    numbering[parcel.street_name] = ordinal + 1
    number = house_number(ordinal, ordinal % 2)
    address = f"{number} {parcel.street_name}".strip() if parcel.street_name else ""

    parcel.use = LandUse.BUILDING
    parcel.building_id = building.building_id

    return BuildingPlacement(
        building_id=building.building_id,
        kind=building.kind,
        district_id=shape.district_id,
        parcel_id=parcel.parcel_id,
        footprint=[g.round_point(p) for p in footprint],
        centre=g.round_point(centre),
        angle=round(angle, 6),
        width_m=round(width, 2),
        depth_m=round(depth, 2),
        floors=floors,
        height_m=round(height, 2),
        entrance=g.round_point(entrance),
        access_node=_nearest_node(network, entrance),
        address=address,
    )


# -- open ground ------------------------------------------------------------------


def _open_ground(
    shape: DistrictShape,
    spare: Iterable[Parcel],
    spaces: dict[str, OpenSpace],
    registry: NameRegistry,
) -> None:
    """Plots with no building stay plots. They are named, and they stay empty."""

    pool = registry.pool(derive_seed(shape.seed, "open"), shape.kind)
    rng = DeterministicRng(derive_seed(shape.seed, "open-use"))
    for index, parcel in enumerate(sorted(spare, key=lambda p: p.parcel_id)):
        use = _open_use(shape.kind, parcel, rng)
        parcel.use = use
        name = pool.open_space(use.value, index) if use in (LandUse.PARK, LandUse.PLAZA) else ""
        spaces[parcel.parcel_id] = OpenSpace(
            space_id=parcel.parcel_id,
            district_id=shape.district_id,
            parcel_id=parcel.parcel_id,
            use=use,
            polygon=list(parcel.polygon),
            centre=parcel.centre,
            name=name,
        )


def _open_use(district_kind: str, parcel: Parcel, rng: DeterministicRng) -> LandUse:
    if district_kind in YARD_KINDS:
        return LandUse.YARD if rng.chance(0.72) else LandUse.VACANT
    if parcel.area_m2 > 3_000.0 and rng.chance(0.45):
        return LandUse.PARK
    if rng.chance(0.18):
        return LandUse.PLAZA
    return LandUse.PARK if rng.chance(0.5) else LandUse.VACANT


# -- helpers ----------------------------------------------------------------------


def _major_street_points(network: StreetNetwork) -> list[Vec2]:
    points: list[Vec2] = []
    for segment in network.segments.values():
        if segment.klass is StreetClass.LOCAL:
            continue
        a = network.nodes.get(segment.a)
        b = network.nodes.get(segment.b)
        if a and b:
            points.append(g.lerp(a.point, b.point, 0.5))
    return points


def _nearest_node(network: StreetNetwork, point: Vec2) -> str:
    best: tuple[float, str] | None = None
    for node_id in sorted(network.nodes):
        d = g.distance(network.nodes[node_id].point, point)
        if best is None or d < best[0]:
            best = (d, node_id)
    return best[1] if best else ""
