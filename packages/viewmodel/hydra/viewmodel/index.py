"""The shared ordering that lets frames talk in integers.

A city frame refers to buildings and districts by position, not by name: ``17`` instead of
``"building_00017"``. That is most of the difference between a twenty kilobyte tick and a
two hundred kilobyte one.

For that to work, two processes that never speak to each other -- the worker writing frames
and the API serving the projection -- have to agree on the order. They agree by both sorting
the ids, which needs no coordination, no shared state and no version negotiation. The order
is written into the projection payload as well, so a client can always check.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hydra.geography.model import GeographyState


@dataclass(slots=True)
class CityIndex:
    buildings: list[str] = field(default_factory=list)
    districts: list[str] = field(default_factory=list)
    _building_pos: dict[str, int] = field(default_factory=dict, repr=False)
    _district_pos: dict[str, int] = field(default_factory=dict, repr=False)

    @property
    def building_positions(self) -> dict[str, int]:
        """The id-to-index map itself.

        Exposed because frame building looks up five thousand ids per frame, and going
        through :meth:`building` for each one adds a Python call per person for nothing.
        """

        return self._building_pos

    def building(self, building_id: str) -> int:
        return self._building_pos.get(building_id, -1)

    def district(self, district_id: str) -> int:
        return self._district_pos.get(district_id, -1)

    def building_at(self, position: int) -> str:
        return self.buildings[position] if 0 <= position < len(self.buildings) else ""

    def district_at(self, position: int) -> str:
        return self.districts[position] if 0 <= position < len(self.districts) else ""


def build_index(geography: GeographyState, city_id: str = "") -> CityIndex:
    target = city_id or geography.seed_city_id
    city = geography.cities[target]
    districts = sorted(city.district_ids)
    known = set(districts)
    buildings = sorted(
        b for b in geography.buildings if geography.buildings[b].district_id in known
    )
    return CityIndex(
        buildings=buildings,
        districts=districts,
        _building_pos={b: i for i, b in enumerate(buildings)},
        _district_pos={d: i for i, d in enumerate(districts)},
    )
