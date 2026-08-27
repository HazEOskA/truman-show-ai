"""The projection engine's entry point.

Five stages, one direction, no feedback:

    territory -> streets -> parcels -> placement -> network

Each stage reads what the ones before it produced and nothing else, which is what makes the
whole thing a pure function. Call it with the same :class:`~hydra.spatial.source.CityInput`
and you get the same city -- so the projection can be cached by its inputs alone, computed
once per world, and shared by every viewer.

This never runs inside the tick loop. It runs when a world is first opened for viewing, and
again only if a building is added or a district changes shape.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from hydra.kernel.serialization import content_hash

from . import geometry as g
from .model import Bounds, CityProjection, PROJECTION_VERSION
from .naming import NameRegistry
from .network import build_transit
from .parcels import build_parcels
from .placement import build_placements
from .source import CityInput, from_geography
from .streets import build_streets
from .territory import build_territory

if TYPE_CHECKING:                                    # pragma: no cover - typing only
    from hydra.geography.model import GeographyState


def projection_key(city: CityInput) -> str:
    """The cache key: version plus everything the layout depends on.

    Cheap by design -- it must be computable without running the pipeline, which is the
    whole point of a cache key.
    """

    return content_hash({"version": PROJECTION_VERSION, "input": city.input_hash()})


def project_city(city: CityInput) -> CityProjection:
    started = time.perf_counter()
    timings: dict[str, float] = {}

    # One registry for the whole city: no two streets, parks or squares share a name, so an
    # address always identifies exactly one place.
    names = NameRegistry()

    boundary, shapes, territory_report = build_territory(city)
    timings["territory_ms"] = _lap(started)

    mark = time.perf_counter()
    network, lattices, street_report = build_streets(city.seed, boundary, shapes, names)
    timings["streets_ms"] = _lap(mark)

    mark = time.perf_counter()
    blocks, parcels, parcel_report = build_parcels(shapes, lattices)
    timings["parcels_ms"] = _lap(mark)

    mark = time.perf_counter()
    placements, spaces, placement_report = build_placements(city, shapes, parcels, network, names)
    timings["placement_ms"] = _lap(mark)

    mark = time.perf_counter()
    stops, lines, transit_report = build_transit(city.seed, shapes, network, placements)
    timings["transit_ms"] = _lap(mark)

    min_x, min_y, max_x, max_y = g.bbox(boundary) if boundary else (0.0, 0.0, 0.0, 0.0)
    projection = CityProjection(
        world_seed=city.seed,
        city_id=city.city_id,
        projection_version=PROJECTION_VERSION,
        projection_hash=projection_key(city),
        bounds=Bounds(min_x, min_y, max_x, max_y),
        boundary=boundary,
        districts=shapes,
        streets=network,
        blocks=blocks,
        parcels=parcels,
        buildings=placements,
        open_spaces=spaces,
        transit_stops=stops,
        transit_lines=lines,
    )
    projection.report = {
        "territory": territory_report,
        "streets": street_report,
        "parcels": parcel_report,
        "placement": placement_report,
        "transit": transit_report,
        "timings": timings,
        "total_ms": _lap(started),
    }
    return projection


def project_world(geography: "GeographyState", seed: int, city_id: str = "") -> CityProjection:
    """Project the seed city of a live world. Reads state; never writes it."""

    return project_city(from_geography(geography, city_id, seed=seed))


def content_digest(projection: CityProjection) -> str:
    """Digest of the produced geometry, for proving the pipeline is deterministic.

    Distinct from ``projection_hash``, which digests the *inputs*. Two runs that agree on
    inputs but disagree here would mean the engine itself had become non-deterministic.
    """

    payload = {
        "boundary": projection.boundary,
        "districts": [
            [d.district_id, d.polygon, d.built_polygon, d.grid_angle, d.block_size_m]
            for d in sorted(projection.districts.values(), key=lambda x: x.district_id)
        ],
        "nodes": [[n.node_id, n.point] for n in sorted(projection.streets.nodes.values(), key=lambda x: x.node_id)],
        "segments": [
            [s.segment_id, s.a, s.b, s.klass.value, s.width_m, s.name]
            for s in sorted(projection.streets.segments.values(), key=lambda x: x.segment_id)
        ],
        "parcels": [
            [p.parcel_id, p.polygon, p.use.value, p.building_id, p.street_name]
            for p in sorted(projection.parcels.values(), key=lambda x: x.parcel_id)
        ],
        "buildings": [
            [b.building_id, b.footprint, b.centre, b.angle, b.floors, b.height_m, b.address]
            for b in sorted(projection.buildings.values(), key=lambda x: x.building_id)
        ],
        "transit": [
            [l.line_id, l.name, l.path]
            for l in sorted(projection.transit_lines.values(), key=lambda x: x.line_id)
        ],
    }
    return content_hash(payload)


class ProjectionCache:
    """Keeps the last few projections in memory, keyed by their inputs.

    Small on purpose: a projection is a few megabytes and a process usually looks at one
    world, occasionally two when comparing forks.
    """

    __slots__ = ("_limit", "_entries")

    def __init__(self, limit: int = 4) -> None:
        self._limit = max(1, limit)
        self._entries: dict[str, CityProjection] = {}

    def get(self, city: CityInput) -> CityProjection:
        key = projection_key(city)
        cached = self._entries.pop(key, None)
        if cached is None:
            cached = project_city(city)
        self._entries[key] = cached                  # re-insert: dicts keep insertion order
        while len(self._entries) > self._limit:
            oldest = next(iter(self._entries))
            del self._entries[oldest]
        return cached

    def peek(self, key: str) -> CityProjection | None:
        return self._entries.get(key)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


def _lap(since: float) -> float:
    return round((time.perf_counter() - since) * 1000.0, 2)
