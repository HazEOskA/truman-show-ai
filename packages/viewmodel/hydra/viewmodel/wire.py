"""Turning a projection into something a browser can download once.

The projection holds explicit geometry: four corners per footprint, four per plot, a point
per street node. Sent that way it is around three hundred kilobytes of mostly redundant
numbers, because every rectangle in the city is described twice -- once by its corners and
once, implicitly, by the fact that it is a rectangle.

So the wire form sends rectangles as ``[x, y, width, depth, angle]`` and lets the renderer
rebuild the corners. That is smaller *and* more useful: a sprite needs the centre and the
rotation anyway, and reconstructing corners from them is one line of shader-friendly maths.

Coordinates go out rounded to a decimetre. Nothing in a city view is decided by a
centimetre, and the extra digits are pure payload.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from hydra.spatial import geometry
from hydra.spatial.model import CityProjection, Vec2

from .index import CityIndex

PRECISION = 1


def _n(value: float) -> float:
    return round(value, PRECISION) + 0.0


def _flat(points: Sequence[Vec2]) -> list[float]:
    out: list[float] = []
    for x, y in points:
        out.append(_n(x))
        out.append(_n(y))
    return out


def projection_payload(projection: CityProjection, index: CityIndex) -> dict[str, Any]:
    """Everything the renderer needs to draw a still city, in index order."""

    district_order = index.districts
    district_pos = {d: i for i, d in enumerate(district_order)}

    streets = projection.streets
    node_order = sorted(streets.nodes)
    node_pos = {n: i for i, n in enumerate(node_order)}

    names: list[str] = []
    name_pos: dict[str, int] = {}

    def name_index(name: str) -> int:
        if not name:
            return -1
        if name not in name_pos:
            name_pos[name] = len(names)
            names.append(name)
        return name_pos[name]

    segments = [streets.segments[s] for s in sorted(streets.segments)]
    klasses = ("arterial", "collector", "local")
    klass_pos = {k: i for i, k in enumerate(klasses)}

    parcels = [projection.parcels[p] for p in sorted(projection.parcels)]
    parcel_pos = {p.parcel_id: i for i, p in enumerate(parcels)}
    uses = ("building", "park", "plaza", "yard", "water", "vacant")
    use_pos = {u: i for i, u in enumerate(uses)}

    buildings = []
    for building_id in index.buildings:
        placement = projection.buildings.get(building_id)
        if placement is None:
            buildings.append(None)
            continue
        buildings.append(placement)

    return {
        "projection_hash": projection.projection_hash,
        "projection_version": projection.projection_version,
        "city_id": projection.city_id,
        "bounds": {
            "min_x": _n(projection.bounds.min_x),
            "min_y": _n(projection.bounds.min_y),
            "max_x": _n(projection.bounds.max_x),
            "max_y": _n(projection.bounds.max_y),
        },
        "boundary": _flat(projection.boundary),
        "order": {"buildings": index.buildings, "districts": district_order},
        "districts": [
            {
                "id": shape.district_id,
                "name": shape.name,
                "kind": shape.kind,
                "polygon": _flat(shape.polygon),
                "built": _flat(shape.built_polygon),
                "centre": [_n(shape.centre[0]), _n(shape.centre[1])],
                "area_m2": _n(shape.area_m2),
                "angle": round(shape.grid_angle, 5),
                "block_m": _n(shape.block_size_m),
            }
            for shape in (projection.districts[d] for d in district_order)
        ],
        "streets": {
            "nodes": _flat([streets.nodes[n].point for n in node_order]),
            "a": [node_pos[s.a] for s in segments],
            "b": [node_pos[s.b] for s in segments],
            "klass": [klass_pos.get(s.klass.value, 2) for s in segments],
            "width": [_n(s.width_m) for s in segments],
            "name": [name_index(s.name) for s in segments],
            "klasses": list(klasses),
        },
        "parcels": {
            "rect": _rects(parcels),
            "use": [use_pos.get(p.use.value, 5) for p in parcels],
            "district": [district_pos.get(p.district_id, -1) for p in parcels],
            "uses": list(uses),
        },
        "buildings": {
            "rect": _rects(buildings),
            "kind": [b.kind if b else "" for b in buildings],
            "floors": [b.floors if b else 0 for b in buildings],
            "height": [_n(b.height_m) if b else 0.0 for b in buildings],
            "district": [district_pos.get(b.district_id, -1) if b else -1 for b in buildings],
            "parcel": [parcel_pos.get(b.parcel_id, -1) if b else -1 for b in buildings],
            "entrance": _flat([b.entrance if b else (0.0, 0.0) for b in buildings]),
            "address": [b.address if b else "" for b in buildings],
        },
        "transit": {
            "lines": [
                {
                    "id": line.line_id,
                    "name": line.name,
                    "colour": line.colour,
                    "path": _flat(line.path),
                    "stops": list(line.stop_ids),
                }
                for line in (projection.transit_lines[l] for l in sorted(projection.transit_lines))
            ],
            "stops": [
                {
                    "id": stop.stop_id,
                    "name": stop.name,
                    "point": [_n(stop.point[0]), _n(stop.point[1])],
                    "district": district_pos.get(stop.district_id, -1),
                }
                for stop in (projection.transit_stops[s] for s in sorted(projection.transit_stops))
            ],
        },
        "street_names": names,
        "report": projection.report,
    }


def _rects(items: Sequence[Any | None]) -> list[float]:
    """``[x, y, width, depth, angle]`` per item, flattened; five zeros for a gap.

    Placements and parcels both carry a centre, an extent and an angle, so both collapse to
    five numbers instead of eight coordinates -- and the renderer wants exactly those five.
    """

    out: list[float] = []
    for item in items:
        if item is None:
            out.extend((0.0, 0.0, 0.0, 0.0, 0.0))
            continue
        centre = item.centre
        if hasattr(item, "width_m"):
            width, depth, angle = item.width_m, item.depth_m, item.angle
        else:
            width, depth, angle = _extent_of(item)
        out.extend((_n(centre[0]), _n(centre[1]), _n(width), _n(depth), round(angle, 5)))
    return out


def _extent_of(parcel: Any) -> tuple[float, float, float]:
    """A parcel's rectangle, measured in the frame its own frontage defines."""

    angle = (parcel.frontage_angle + math.pi * 0.5) % math.tau
    width, depth = geometry.oriented_extent(parcel.polygon, angle)
    return (width, depth, angle)
