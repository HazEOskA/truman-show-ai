"""Stage 3 -- blocks and parcels.

A block is one cell of a district's lattice, inset by half the width of each of the four
streets around it. Because the lattice is axis-aligned in the district's own rotated frame,
blocks are exact rectangles there, and subdividing them is arithmetic rather than geometry:
split along the longer side, recurse, stop at one parcel.

Every parcel comes out knowing which street it faces and which way it faces it. That single
fact is what later lets buildings sit square to the road with their doors on the pavement,
instead of floating at arbitrary angles -- the difference between a city and a scatter plot.
"""

from __future__ import annotations

import math

from . import geometry as g
from .model import Block, DistrictShape, Lattice, Parcel, Vec2
from .zoning import parcels_per_block

#: A parcel narrower than this is not worth keeping as a separate plot.
MIN_PARCEL_M = 12.0
MIN_PARCEL_AREA_M2 = 260.0


def build_parcels(
    shapes: dict[str, DistrictShape], lattices: dict[str, Lattice]
) -> tuple[dict[str, Block], dict[str, Parcel], dict[str, object]]:
    blocks: dict[str, Block] = {}
    parcels: dict[str, Parcel] = {}

    for district_id in sorted(shapes):
        lattice = lattices.get(district_id)
        if lattice is None or not lattice.nodes:
            continue
        shape = shapes[district_id]
        count = parcels_per_block(shape.kind)
        for (i, j) in sorted(_complete_cells(lattice)):
            block = _block(lattice, shape, i, j)
            if block is None:
                continue
            blocks[block.block_id] = block
            for parcel in _subdivide(block, lattice, i, j, count):
                parcels[parcel.parcel_id] = parcel
                block.parcel_ids.append(parcel.parcel_id)

    report = {
        "blocks": len(blocks),
        "parcels": len(parcels),
        "parcel_area_m2": round(sum(p.area_m2 for p in parcels.values()), 2),
    }
    return (blocks, parcels, report)


def _complete_cells(lattice: Lattice) -> list[tuple[int, int]]:
    """Cells with all four corners present. Anything less is street, not block."""

    nodes = lattice.nodes
    return [
        (i, j)
        for (i, j) in nodes
        if (i + 1, j) in nodes and (i, j + 1) in nodes and (i + 1, j + 1) in nodes
    ]


def _block(lattice: Lattice, shape: DistrictShape, i: int, j: int) -> Block | None:
    """The cell rectangle, inset by half of each bounding street's width."""

    s = lattice.spacing
    u0 = lattice.origin_u + i * s
    v0 = lattice.origin_v + j * s
    left = lattice.column_width.get(i, 8.0) * 0.5
    right = lattice.column_width.get(i + 1, 8.0) * 0.5
    bottom = lattice.row_width.get(j, 8.0) * 0.5
    top = lattice.row_width.get(j + 1, 8.0) * 0.5

    lo_u, hi_u = u0 + left, u0 + s - right
    lo_v, hi_v = v0 + bottom, v0 + s - top
    if hi_u - lo_u < MIN_PARCEL_M or hi_v - lo_v < MIN_PARCEL_M:
        return None

    polygon = [
        _world(lattice, lo_u, lo_v),
        _world(lattice, hi_u, lo_v),
        _world(lattice, hi_u, hi_v),
        _world(lattice, lo_u, hi_v),
    ]
    return Block(
        block_id=f"blk_{shape.district_id}_{i}_{j}",
        district_id=shape.district_id,
        polygon=[g.round_point(p) for p in polygon],
        angle=lattice.angle,
        area_m2=round((hi_u - lo_u) * (hi_v - lo_v), 2),
    )


def _subdivide(block: Block, lattice: Lattice, i: int, j: int, count: int) -> list[Parcel]:
    """Split the block rectangle into ``count`` plots, each fronting a real street."""

    s = lattice.spacing
    u0 = lattice.origin_u + i * s
    v0 = lattice.origin_v + j * s
    lo_u = u0 + lattice.column_width.get(i, 8.0) * 0.5
    hi_u = u0 + s - lattice.column_width.get(i + 1, 8.0) * 0.5
    lo_v = v0 + lattice.row_width.get(j, 8.0) * 0.5
    hi_v = v0 + s - lattice.row_width.get(j + 1, 8.0) * 0.5

    rects = _split_rect((lo_u, lo_v, hi_u, hi_v), max(1, count))
    parcels: list[Parcel] = []
    for index, (a_u, a_v, b_u, b_v) in enumerate(rects):
        width, depth = b_u - a_u, b_v - a_v
        if width < MIN_PARCEL_M or depth < MIN_PARCEL_M or width * depth < MIN_PARCEL_AREA_M2:
            continue
        polygon = [
            _world(lattice, a_u, a_v),
            _world(lattice, b_u, a_v),
            _world(lattice, b_u, b_v),
            _world(lattice, a_u, b_v),
        ]
        side, frontage_u, frontage_v = _frontage(
            (a_u, a_v, b_u, b_v), (lo_u, lo_v, hi_u, hi_v)
        )
        parcels.append(
            Parcel(
                parcel_id=f"{block.block_id}_p{index}",
                block_id=block.block_id,
                district_id=block.district_id,
                polygon=[g.round_point(p) for p in polygon],
                centre=g.round_point(_world(lattice, (a_u + b_u) * 0.5, (a_v + b_v) * 0.5)),
                area_m2=round(width * depth, 2),
                frontage_angle=round((lattice.angle + side * math.pi * 0.5) % math.tau, 6),
                frontage_point=g.round_point(_world(lattice, frontage_u, frontage_v)),
                street_id=_street_for(lattice, i, j, side),
                street_name=_street_name(lattice, i, j, side),
            )
        )
    return parcels


def _split_rect(rect: tuple[float, float, float, float], count: int) -> list[tuple[float, float, float, float]]:
    """Recursively halve along the longer side until ``count`` plots remain."""

    if count <= 1:
        return [rect]
    a_u, a_v, b_u, b_v = rect
    left_count = count // 2
    share = left_count / count
    if (b_u - a_u) >= (b_v - a_v):
        cut = a_u + (b_u - a_u) * share
        return _split_rect((a_u, a_v, cut, b_v), left_count) + _split_rect(
            (cut, a_v, b_u, b_v), count - left_count
        )
    cut = a_v + (b_v - a_v) * share
    return _split_rect((a_u, a_v, b_u, cut), left_count) + _split_rect(
        (a_u, cut, b_u, b_v), count - left_count
    )


def _frontage(
    parcel: tuple[float, float, float, float], block: tuple[float, float, float, float]
) -> tuple[int, float, float]:
    """Which block edge this plot sits on: ``(side, u, v)`` of the frontage midpoint.

    Sides are numbered anticlockwise from the block's local +u edge, so ``side * 90°`` added
    to the district angle gives the outward normal.
    """

    a_u, a_v, b_u, b_v = parcel
    lo_u, lo_v, hi_u, hi_v = block
    mid_u, mid_v = (a_u + b_u) * 0.5, (a_v + b_v) * 0.5
    gaps = (
        (hi_u - b_u, 0, (b_u, mid_v)),      # +u
        (hi_v - b_v, 1, (mid_u, b_v)),      # +v
        (a_u - lo_u, 2, (a_u, mid_v)),      # -u
        (a_v - lo_v, 3, (mid_u, a_v)),      # -v
    )
    _, side, point = min(gaps, key=lambda item: (item[0], item[1]))
    return (side, point[0], point[1])


def _street_for(lattice: Lattice, i: int, j: int, side: int) -> str:
    """The segment a plot on this side of cell ``(i, j)`` fronts onto."""

    if side == 0:
        return lattice.column_segment.get((i + 1, j), "")
    if side == 1:
        return lattice.row_segment.get((i, j + 1), "")
    if side == 2:
        return lattice.column_segment.get((i, j), "")
    return lattice.row_segment.get((i, j), "")


def _street_name(lattice: Lattice, i: int, j: int, side: int) -> str:
    if side == 0:
        return lattice.column_name.get(i + 1, "")
    if side == 1:
        return lattice.row_name.get(j + 1, "")
    if side == 2:
        return lattice.column_name.get(i, "")
    return lattice.row_name.get(j, "")


def _world(lattice: Lattice, u: float, v: float) -> Vec2:
    return g.rotate((u, v), lattice.angle)
