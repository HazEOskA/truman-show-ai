"""Spatial Projection Engine.

Hydra's geography knows which district a building belongs to. It does not know where the
building stands, which street it faces, or how to walk from one to another -- because the
simulation never needed to. This package answers those questions *without* changing the
simulation: it is a pure, deterministic reading of world state, computed outside the tick
loop and thrown away freely.

    world seed + districts + buildings  ->  CityProjection

The same world always projects to the same city, on any machine and in every fork, because
nothing here depends on wall-clock time, dict iteration order, ``random`` or ``hash()``.
The engine is read-only: it imports geography's *types* and never touches its state.
"""

from __future__ import annotations

from .model import (
    Block,
    Bounds,
    BuildingPlacement,
    CityProjection,
    DistrictShape,
    LandUse,
    OpenSpace,
    Parcel,
    StreetClass,
    StreetNetwork,
    StreetNode,
    StreetSegment,
    TransitLine,
    TransitStop,
    PROJECTION_VERSION,
)
from .network import path_points, shortest_path, transit_path
from .projection import (
    ProjectionCache,
    content_digest,
    project_city,
    project_world,
    projection_key,
)
from .source import BuildingInput, CityInput, DistrictInput, from_geography

__all__ = [
    "Block",
    "Bounds",
    "BuildingInput",
    "BuildingPlacement",
    "CityInput",
    "CityProjection",
    "DistrictInput",
    "DistrictShape",
    "LandUse",
    "OpenSpace",
    "PROJECTION_VERSION",
    "Parcel",
    "ProjectionCache",
    "StreetClass",
    "StreetNetwork",
    "StreetNode",
    "StreetSegment",
    "TransitLine",
    "TransitStop",
    "content_digest",
    "from_geography",
    "path_points",
    "project_city",
    "project_world",
    "projection_key",
    "shortest_path",
    "transit_path",
]
