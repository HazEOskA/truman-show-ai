"""What a projection is.

A :class:`CityProjection` is the spatial reading of a world, not a part of it. Nothing here
is a :class:`~hydra.kernel.state.DomainState`: the projection is derived, cacheable and
throwaway, and the kernel neither knows nor needs it. It answers exactly one question --
*where is everything* -- for a world whose geography records only which district a thing
belongs to.

Units are metres throughout, with the origin at the seed city's centre.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

Vec2 = tuple[float, float]

#: Bumped whenever the generated layout would change for the same inputs. The renderer
#: caches by ``projection_hash``, which folds this in, so a bump invalidates every cache.
PROJECTION_VERSION = "1.0.0"


class StreetClass(str, enum.Enum):
    ARTERIAL = "arterial"       # between districts, carries transit
    COLLECTOR = "collector"     # district spine
    LOCAL = "local"             # block edges


class LandUse(str, enum.Enum):
    BUILDING = "building"       # a real Building from world state stands here
    PARK = "park"
    PLAZA = "plaza"
    YARD = "yard"               # service / industrial open ground
    WATER = "water"
    VACANT = "vacant"


@dataclass(slots=True)
class Bounds:
    min_x: float = 0.0
    min_y: float = 0.0
    max_x: float = 0.0
    max_y: float = 0.0

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def centre(self) -> Vec2:
        return ((self.min_x + self.max_x) * 0.5, (self.min_y + self.max_y) * 0.5)


@dataclass(slots=True)
class DistrictShape:
    """A district's administrative polygon and the built-up fabric inside it.

    Hydra's districts are municipal areas -- 66 km² for 664 buildings -- so the settlement
    occupies only part of each one. ``polygon`` is the boundary that layers and choropleths
    colour; ``built_polygon`` is where streets, parcels and buildings actually go. The gap
    between them is open land, and it is left empty rather than filled with invented
    structures.
    """

    district_id: str
    name: str
    kind: str
    polygon: list[Vec2]
    centre: Vec2
    area_m2: float
    built_polygon: list[Vec2] = field(default_factory=list)
    built_area_m2: float = 0.0
    grid_angle: float = 0.0        # radians; the local street orientation
    block_size_m: float = 180.0
    seed: int = 0


@dataclass(slots=True)
class StreetNode:
    node_id: str
    point: Vec2
    district_id: str = ""


@dataclass(slots=True)
class StreetSegment:
    segment_id: str
    a: str                          # node id
    b: str                          # node id
    klass: StreetClass
    width_m: float
    length_m: float
    district_id: str = ""
    name: str = ""


@dataclass(slots=True)
class StreetNetwork:
    nodes: dict[str, StreetNode] = field(default_factory=dict)
    segments: dict[str, StreetSegment] = field(default_factory=dict)
    #: node id -> [(neighbour node id, segment id, length_m)]
    adjacency: dict[str, list[tuple[str, str, float]]] = field(default_factory=dict)

    def add_node(self, node: StreetNode) -> None:
        self.nodes[node.node_id] = node
        self.adjacency.setdefault(node.node_id, [])

    def add_segment(self, segment: StreetSegment) -> None:
        self.segments[segment.segment_id] = segment
        self.adjacency.setdefault(segment.a, []).append((segment.b, segment.segment_id, segment.length_m))
        self.adjacency.setdefault(segment.b, []).append((segment.a, segment.segment_id, segment.length_m))


@dataclass(slots=True)
class Lattice:
    """The regular grid a district's local streets were laid on.

    Handed from the street stage to the parcel stage so blocks can be read straight off the
    grid instead of being recovered by parsing node ids or re-extracting planar faces.
    Coordinates ``(u, v)`` are in the district's own rotated frame.
    """

    district_id: str
    angle: float
    spacing: float
    origin_u: float
    origin_v: float
    nodes: dict[tuple[int, int], str] = field(default_factory=dict)
    column_width: dict[int, float] = field(default_factory=dict)
    row_width: dict[int, float] = field(default_factory=dict)
    column_name: dict[int, str] = field(default_factory=dict)
    row_name: dict[int, str] = field(default_factory=dict)
    column_segment: dict[tuple[int, int], str] = field(default_factory=dict)
    row_segment: dict[tuple[int, int], str] = field(default_factory=dict)


@dataclass(slots=True)
class Block:
    block_id: str
    district_id: str
    polygon: list[Vec2]
    angle: float
    area_m2: float
    parcel_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Parcel:
    parcel_id: str
    block_id: str
    district_id: str
    polygon: list[Vec2]
    centre: Vec2
    area_m2: float
    frontage_angle: float           # facing direction, radians
    frontage_point: Vec2            # where the plot meets its street
    street_id: str = ""
    street_name: str = ""
    use: LandUse = LandUse.VACANT
    building_id: str = ""


@dataclass(slots=True)
class BuildingPlacement:
    building_id: str
    kind: str
    district_id: str
    parcel_id: str
    footprint: list[Vec2]
    centre: Vec2
    angle: float
    width_m: float
    depth_m: float
    floors: int
    height_m: float
    entrance: Vec2
    access_node: str = ""
    address: str = ""


@dataclass(slots=True)
class OpenSpace:
    space_id: str
    district_id: str
    parcel_id: str
    use: LandUse
    polygon: list[Vec2]
    centre: Vec2
    name: str = ""


@dataclass(slots=True)
class TransitStop:
    stop_id: str
    point: Vec2
    district_id: str
    node_id: str
    name: str = ""


@dataclass(slots=True)
class TransitLine:
    line_id: str
    name: str
    stop_ids: list[str]
    path: list[Vec2]
    colour: str = "#4bd6ff"


@dataclass(slots=True)
class CityProjection:
    """The complete spatial reading of one city, for one projection version."""

    world_seed: int
    city_id: str
    projection_version: str = PROJECTION_VERSION
    projection_hash: str = ""
    bounds: Bounds = field(default_factory=Bounds)
    boundary: list[Vec2] = field(default_factory=list)
    districts: dict[str, DistrictShape] = field(default_factory=dict)
    streets: StreetNetwork = field(default_factory=StreetNetwork)
    blocks: dict[str, Block] = field(default_factory=dict)
    parcels: dict[str, Parcel] = field(default_factory=dict)
    buildings: dict[str, BuildingPlacement] = field(default_factory=dict)
    open_spaces: dict[str, OpenSpace] = field(default_factory=dict)
    transit_stops: dict[str, TransitStop] = field(default_factory=dict)
    transit_lines: dict[str, TransitLine] = field(default_factory=dict)
    #: Diagnostics: unplaced building ids, area error per district, timings.
    report: dict[str, object] = field(default_factory=dict)

    def district_of_building(self, building_id: str) -> str:
        placement = self.buildings.get(building_id)
        return placement.district_id if placement else ""

    def point_of_building(self, building_id: str) -> Vec2 | None:
        placement = self.buildings.get(building_id)
        return placement.centre if placement else None
