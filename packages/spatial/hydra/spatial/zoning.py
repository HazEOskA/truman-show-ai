"""Plot sizes, footprints and heights per building kind.

These are the only "invented" numbers in the projection, and they are invented once, here,
where they can be read and argued with -- not scattered through the placement code. They
answer questions world state does not: a ``Building`` knows it houses 100 people, but not
how wide it is or how many floors that takes.

Everything is derived from ``capacity`` where capacity means something spatial, and falls
back to a per-kind default where it does not. Nothing here feeds back into the simulation.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_KIND = "housing"


@dataclass(frozen=True, slots=True)
class KindZoning:
    #: Typical plot the building sits on, in m². Drives how much land a district needs.
    plot_m2: float
    #: m² of floor area per unit of ``capacity``.
    floor_per_capacity: float
    #: Floors when capacity gives no better answer.
    base_floors: int
    #: Storey height in metres.
    storey_m: float
    #: Fraction of the plot the footprint may cover.
    coverage: float
    #: width / depth of the footprint.
    aspect: float
    #: Larger values pull the kind toward the district's main streets.
    frontage_pull: float
    #: Larger values push the kind toward the district edge.
    edge_pull: float


ZONING: dict[str, KindZoning] = {
    "housing":       KindZoning(2600, 34.0, 4, 3.0, 0.42, 1.35, 0.35, 0.00),
    "retail":        KindZoning(1200, 22.0, 2, 4.0, 0.62, 1.60, 1.00, 0.00),
    "office":        KindZoning(2000, 16.0, 6, 3.6, 0.48, 1.15, 0.75, 0.00),
    "factory":       KindZoning(12000, 55.0, 1, 8.0, 0.55, 1.70, 0.20, 0.70),
    "school":        KindZoning(9000, 9.0, 3, 3.8, 0.30, 1.50, 0.30, 0.15),
    "university":    KindZoning(40000, 9.0, 4, 4.0, 0.26, 1.25, 0.35, 0.25),
    "hospital":      KindZoning(14000, 22.0, 7, 3.8, 0.34, 1.20, 0.55, 0.10),
    "police":        KindZoning(2500, 18.0, 3, 3.6, 0.42, 1.20, 0.70, 0.00),
    "court":         KindZoning(3500, 24.0, 3, 5.0, 0.40, 1.30, 0.80, 0.00),
    "city_hall":     KindZoning(6000, 20.0, 4, 4.6, 0.38, 1.40, 1.00, 0.00),
    "power_plant":   KindZoning(30000, 900.0, 1, 14.0, 0.42, 1.55, 0.10, 0.90),
    "water_plant":   KindZoning(20000, 0.0, 1, 9.0, 0.34, 1.45, 0.10, 0.90),
    "data_centre":   KindZoning(6000, 60.0, 2, 6.0, 0.55, 1.30, 0.15, 0.55),
    "transport_hub": KindZoning(25000, 1.6, 2, 7.0, 0.30, 2.10, 0.95, 0.30),
    "culture":       KindZoning(5000, 12.0, 2, 6.0, 0.40, 1.35, 0.85, 0.05),
}

#: Fraction of built-up land that stays open: yards, parks, plazas, car parks.
OPEN_RATIO: dict[str, float] = {
    "commercial": 0.24,
    "elite": 0.44,
    "mixed": 0.28,
    "residential": 0.32,
    "industrial": 0.30,
    "port": 0.34,
    "periphery": 0.30,
}

#: Parcels per block, by district kind. Industry gets one big plot per block.
PARCELS_PER_BLOCK: dict[str, int] = {
    "commercial": 6,
    "elite": 3,
    "mixed": 6,
    "residential": 5,
    "industrial": 2,
    "port": 2,
    "periphery": 4,
}

MIN_BLOCK_M = 64.0
MAX_BLOCK_M = 240.0


def zoning_for(kind: str) -> KindZoning:
    return ZONING.get(kind, ZONING[DEFAULT_KIND])


def plot_area(kind: str) -> float:
    return zoning_for(kind).plot_m2


def open_ratio(district_kind: str) -> float:
    return OPEN_RATIO.get(district_kind, 0.30)


def parcels_per_block(district_kind: str) -> int:
    return PARCELS_PER_BLOCK.get(district_kind, 4)


def footprint_for(kind: str, capacity: int) -> tuple[float, float, int, float]:
    """``(width_m, depth_m, floors, height_m)`` for a building of this kind and capacity.

    Floor area comes from capacity where capacity is a spatial quantity (residents, seats,
    workers); the footprint is then floor area divided by floors, capped by what the plot
    can cover.
    """

    z = zoning_for(kind)
    floor_area = max(0.0, capacity) * z.floor_per_capacity
    if floor_area <= 0.0:
        floor_area = z.plot_m2 * z.coverage * z.base_floors

    max_footprint = z.plot_m2 * z.coverage
    floors = z.base_floors
    # Grow upward before growing outward, but only as far as the kind plausibly goes.
    ceiling = _floor_ceiling(kind, z.base_floors)
    while floors < ceiling and floor_area / floors > max_footprint:
        floors += 1
    footprint = min(max_footprint, floor_area / floors)
    footprint = max(footprint, 45.0)

    width = (footprint * z.aspect) ** 0.5
    depth = footprint / width
    height = floors * z.storey_m
    return (width, depth, floors, height)


def _floor_ceiling(kind: str, base: int) -> int:
    if kind in ("factory", "power_plant", "water_plant", "transport_hub"):
        return max(base, 2)
    if kind in ("housing", "office"):
        return 14
    return max(base + 3, 5)
