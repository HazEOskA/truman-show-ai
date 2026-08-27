"""The engine's input contract.

The projection reads the world; it never touches it. Everything the pipeline needs is
copied into these small immutable records first, for three reasons:

* the stages stay testable without booting a world,
* it is impossible to mutate geography by accident from inside a stage,
* the input set is the cache key -- if none of these fields changed, the projection is
  still valid, whatever else the simulation did.

``area_km2`` and the district hint coordinates are the only geography numbers that matter
here; everything dynamic (population, pollution, occupancy) is a *layer*, not a layout, and
is streamed per tick instead of baked into the projection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

from hydra.kernel.serialization import content_hash

if TYPE_CHECKING:                                    # pragma: no cover - typing only
    from hydra.geography.model import GeographyState


@dataclass(frozen=True, slots=True)
class BuildingInput:
    building_id: str
    kind: str
    district_id: str
    name: str
    capacity: int


@dataclass(frozen=True, slots=True)
class DistrictInput:
    district_id: str
    name: str
    kind: str
    area_km2: float
    hint_x: float                # km, from genesis; a relative arrangement, not a layout
    hint_y: float


@dataclass(frozen=True, slots=True)
class CityInput:
    city_id: str
    name: str
    seed: int
    districts: tuple[DistrictInput, ...] = ()
    buildings: tuple[BuildingInput, ...] = ()

    def buildings_in(self, district_id: str) -> list[BuildingInput]:
        return [b for b in self.buildings if b.district_id == district_id]

    def input_hash(self) -> str:
        """Stable digest of everything the layout depends on."""

        payload = {
            "city_id": self.city_id,
            "seed": self.seed,
            "districts": [
                [d.district_id, d.kind, round(d.area_km2, 6), round(d.hint_x, 6), round(d.hint_y, 6)]
                for d in self.districts
            ],
            "buildings": [[b.building_id, b.kind, b.district_id, b.capacity] for b in self.buildings],
        }
        return content_hash(payload)


def from_geography(geography: "GeographyState", city_id: str = "", *, seed: int = 0) -> CityInput:
    """Read a :class:`CityInput` out of world state. Read-only by construction."""

    target = city_id or geography.seed_city_id
    city = geography.cities[target]
    districts = []
    for district_id in sorted(city.district_ids):
        d = geography.districts[district_id]
        districts.append(
            DistrictInput(
                district_id=d.district_id,
                name=d.name,
                kind=d.kind.value,
                area_km2=float(d.area_km2),
                hint_x=float(d.coordinates.x),
                hint_y=float(d.coordinates.y),
            )
        )
    known = {d.district_id for d in districts}
    buildings = []
    for building_id in sorted(geography.buildings):
        b = geography.buildings[building_id]
        if b.district_id not in known:
            continue
        buildings.append(
            BuildingInput(
                building_id=b.building_id,
                kind=b.kind.value,
                district_id=b.district_id,
                name=b.name,
                capacity=int(b.capacity),
            )
        )
    return CityInput(
        city_id=city.city_id,
        name=city.name,
        seed=seed,
        districts=tuple(districts),
        buildings=tuple(buildings),
    )
