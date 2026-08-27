"""Spatial projection engine: geometry, territory, streets, parcels and placement.

These tests carry the load-bearing promise of the City View: the projection is a *pure
function* of the world's seed and its geography. Same world, same layout, on any machine,
in any fork, forever. If that breaks, the renderer starts lying about where things are.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from hydra.geography.model import GeographyState
from hydra.spatial import geometry as g
from hydra.spatial.model import LandUse, StreetClass
from hydra.spatial.network import path_points, shortest_path
from hydra.spatial.projection import (
    ProjectionCache,
    content_digest,
    project_city,
    project_world,
    projection_key,
)
from hydra.spatial.source import CityInput, DistrictInput, BuildingInput, from_geography
from hydra.spatial.streets import connected_components
from hydra.spatial.territory import build_territory, power_cells


# -- geometry ---------------------------------------------------------------------


SQUARE = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]


def test_polygon_basics():
    assert g.area(SQUARE) == pytest.approx(10_000.0)
    assert g.signed_area(SQUARE) > 0                       # CCW
    assert g.centroid(SQUARE) == pytest.approx((50.0, 50.0))
    assert g.contains(SQUARE, (50.0, 50.0))
    assert not g.contains(SQUARE, (150.0, 50.0))


def test_halfplane_clip_halves_a_square():
    clipped = g.clip_halfplane(SQUARE, (1.0, 0.0), 50.0)
    assert g.area(clipped) == pytest.approx(5_000.0)


def test_inward_offset_shrinks_by_the_setback():
    inset = g.offset_inward(SQUARE, 10.0)
    assert g.area(inset) == pytest.approx(6_400.0)


def test_rectangle_has_the_requested_extent():
    rect = g.rectangle((10.0, 10.0), 20.0, 8.0, 0.0)
    width, depth = g.oriented_extent(rect, 0.0)
    assert width == pytest.approx(20.0)
    assert depth == pytest.approx(8.0)


def test_rotated_rectangle_measures_the_same_in_its_own_frame():
    rect = g.rectangle((0.0, 0.0), 20.0, 8.0, 0.7)
    width, depth = g.oriented_extent(rect, 0.7)
    assert width == pytest.approx(20.0)
    assert depth == pytest.approx(8.0)


def test_simplify_drops_vertices_it_can_spare():
    ring = [(math.cos(t / 40 * math.tau) * 500.0, math.sin(t / 40 * math.tau) * 500.0) for t in range(40)]
    small = g.simplify(ring, 12.0)
    assert len(small) < len(ring)
    assert g.area(small) == pytest.approx(g.area(ring), rel=0.05)


def test_simplify_refuses_to_distort():
    """A tolerance finer than the sampling must leave the ring alone."""

    ring = [(math.cos(t / 40 * math.tau) * 500.0, math.sin(t / 40 * math.tau) * 500.0) for t in range(40)]
    assert len(g.simplify(ring, 1.0)) == len(ring)


# -- territory --------------------------------------------------------------------


def synthetic_city(seed: int = 99) -> CityInput:
    districts = (
        DistrictInput("d_core", "Core", "commercial", 4.2, 0.0, 0.0),
        DistrictInput("d_elite", "Heights", "elite", 6.5, 3.1, 2.6),
        DistrictInput("d_mixed", "Quarter", "mixed", 5.1, -2.4, 1.8),
        DistrictInput("d_res", "West", "residential", 9.4, -5.2, -0.6),
        DistrictInput("d_ind", "Steelgate", "industrial", 11.8, 4.6, -3.4),
    )
    buildings = []
    for district in districts:
        count = 40 if district.kind != "industrial" else 18
        for i in range(count):
            kind = "factory" if district.kind == "industrial" and i % 3 == 0 else "housing"
            buildings.append(
                BuildingInput(f"b_{district.district_id}_{i:03d}", kind, district.district_id, "", 100)
            )
    return CityInput("city_test", "Testopolis", seed, districts, tuple(buildings))


def test_power_cells_tile_the_boundary_without_gaps():
    boundary = [(-1000.0, -1000.0), (1000.0, -1000.0), (1000.0, 1000.0), (-1000.0, 1000.0)]
    sites = [(-400.0, 0.0), (400.0, 0.0), (0.0, 500.0)]
    cells = power_cells(boundary, sites, [0.0, 0.0, 0.0])
    assert sum(g.area(c) for c in cells) == pytest.approx(g.area(boundary), rel=1e-6)


def test_territory_hits_every_district_area():
    city = synthetic_city()
    boundary, shapes, report = build_territory(city)

    assert len(shapes) == len(city.districts)
    assert report["area_fit_max_error"] < 0.02          # every cell within 2% of target
    for district in city.districts:
        shape = shapes[district.district_id]
        assert shape.area_m2 == pytest.approx(district.area_km2 * 1e6, rel=0.02)

    total = sum(s.area_m2 for s in shapes.values())
    assert total == pytest.approx(g.area(boundary), rel=0.01)


def test_district_cells_do_not_overlap():
    _, shapes, _ = build_territory(synthetic_city())
    centres = {k: s.centre for k, s in shapes.items()}
    for district_id, shape in shapes.items():
        for other_id, centre in centres.items():
            if other_id == district_id:
                continue
            assert not g.contains(shape.polygon, centre), f"{other_id} centre fell inside {district_id}"


def test_built_fabric_sits_inside_its_district():
    _, shapes, report = build_territory(synthetic_city())
    for shape in shapes.values():
        assert shape.built_area_m2 > 0.0
        assert shape.built_area_m2 < shape.area_m2
        for point in shape.built_polygon:
            assert g.contains(shape.polygon, point) or g.point_segment_distance(
                point, shape.centre, shape.centre
            ) < shape.area_m2
    assert 0.0 < float(report["built_fraction"]) < 1.0


def test_territory_is_a_pure_function_of_its_input():
    first = build_territory(synthetic_city())
    second = build_territory(synthetic_city())
    assert first[0] == second[0]
    assert {k: v.polygon for k, v in first[1].items()} == {k: v.polygon for k, v in second[1].items()}


def test_a_different_seed_gives_a_different_city():
    a = build_territory(synthetic_city(seed=1))
    b = build_territory(synthetic_city(seed=2))
    assert a[0] != b[0]


def test_degenerate_hints_still_produce_a_city():
    districts = tuple(
        DistrictInput(f"d{i}", f"D{i}", "mixed", 3.0, 0.0, 0.0) for i in range(4)
    )
    city = CityInput("city_flat", "Flat", 7, districts, ())
    boundary, shapes, report = build_territory(city)
    assert len(shapes) == 4
    assert g.area(boundary) > 0.0
    assert report["area_fit_max_error"] < 0.05


# -- against the real world -------------------------------------------------------


def test_projection_reads_the_real_hydra(world):
    geography = world.state.domain(GeographyState)
    city = from_geography(geography, seed=world.state.meta.seed)
    assert city.city_id == geography.seed_city_id
    assert len(city.districts) == len(geography.city().district_ids)
    assert len(city.buildings) == len(geography.buildings)

    boundary, shapes, report = build_territory(city)
    assert len(shapes) == len(city.districts)
    assert report["area_fit_max_error"] < 0.02
    assert g.area(boundary) > 0.0
    for district in city.districts:
        assert shapes[district.district_id].block_size_m >= 64.0


def test_reading_geography_does_not_mutate_it(world):
    geography = world.state.domain(GeographyState)
    before = world.state.state_hash()
    city = from_geography(geography, seed=world.state.meta.seed)
    build_territory(city)
    assert world.state.state_hash() == before


# -- the whole pipeline -----------------------------------------------------------


@pytest.fixture(scope="module")
def projection():
    return project_city(synthetic_city())


def test_every_building_gets_a_plot(projection):
    assert projection.report["placement"]["unplaced"] == 0
    assert len(projection.buildings) == len(synthetic_city().buildings)


def test_no_two_buildings_share_a_plot(projection):
    parcels = [b.parcel_id for b in projection.buildings.values()]
    assert len(parcels) == len(set(parcels))


def test_every_footprint_sits_inside_its_plot(projection):
    for placement in projection.buildings.values():
        parcel = projection.parcels[placement.parcel_id]
        for corner in placement.footprint:
            assert g.contains(parcel.polygon, corner), f"{placement.building_id} overhangs its plot"


def test_buildings_face_their_street(projection):
    """The footprint's short axis runs into the block, not across the pavement."""

    for placement in projection.buildings.values():
        parcel = projection.parcels[placement.parcel_id]
        to_street = g.normalise(g.sub(parcel.frontage_point, parcel.centre))
        if g.length(to_street) < g.EPS:
            continue
        outward = g.normalise(g.sub(placement.entrance, placement.centre))
        assert g.dot(to_street, outward) > 0.5, f"{placement.building_id} has its door round the back"


def test_spare_plots_become_open_ground_not_invented_buildings(projection):
    built = {p.parcel_id for p in projection.parcels.values() if p.use is LandUse.BUILDING}
    assert built == {b.parcel_id for b in projection.buildings.values()}
    for parcel in projection.parcels.values():
        if parcel.use is not LandUse.BUILDING:
            assert parcel.building_id == ""
            assert parcel.parcel_id in projection.open_spaces


def test_the_street_network_is_one_connected_city(projection):
    groups = connected_components(projection.streets)
    assert len(groups) == 1, f"the city is in {len(groups)} pieces"
    assert projection.report["streets"]["components"] == 1


def test_every_building_can_be_reached_from_every_other(projection):
    ids = sorted(projection.buildings)
    first = projection.buildings[ids[0]]
    last = projection.buildings[ids[-1]]
    assert first.access_node in projection.streets.nodes
    assert last.access_node in projection.streets.nodes
    path = shortest_path(projection.streets, first.access_node, last.access_node)
    assert len(path) > 1
    assert g.polyline_length(path_points(projection.streets, path)) > 0.0


def test_streets_have_names_and_buildings_have_addresses(projection):
    named = [s for s in projection.streets.segments.values() if s.klass is not StreetClass.ARTERIAL]
    assert sum(1 for s in named if s.name) > len(named) * 0.9
    with_address = [b for b in projection.buildings.values() if b.address]
    assert len(with_address) > len(projection.buildings) * 0.9


def test_addresses_are_unique(projection):
    addresses = [b.address for b in projection.buildings.values() if b.address]
    assert len(addresses) == len(set(addresses))


# -- purity, the promise the renderer depends on ----------------------------------


def test_the_same_world_always_projects_to_the_same_city():
    first = project_city(synthetic_city())
    second = project_city(synthetic_city())
    assert content_digest(first) == content_digest(second)
    assert first.projection_hash == second.projection_hash


def test_a_changed_world_projects_differently():
    a = synthetic_city()
    b = synthetic_city(seed=a.seed + 1)
    assert projection_key(a) != projection_key(b)
    assert content_digest(project_city(a)) != content_digest(project_city(b))


def test_the_projection_key_ignores_things_that_cannot_move_a_building():
    """Only geometry inputs are in the key. City *name* is not one of them."""

    original = synthetic_city()
    renamed = CityInput(
        original.city_id, "Renamed", original.seed, original.districts, original.buildings
    )
    assert projection_key(original) == projection_key(renamed)


def test_the_cache_returns_the_same_projection_without_recomputing():
    cache = ProjectionCache(limit=2)
    first = cache.get(synthetic_city())
    second = cache.get(synthetic_city())
    assert first is second
    assert len(cache) == 1


def test_the_cache_evicts_the_oldest_world():
    cache = ProjectionCache(limit=2)
    cache.get(synthetic_city(seed=1))
    cache.get(synthetic_city(seed=2))
    cache.get(synthetic_city(seed=3))
    assert len(cache) == 2
    assert cache.peek(projection_key(synthetic_city(seed=1))) is None


# -- against the real world, end to end -------------------------------------------


def test_hydra_projects_completely(world):
    geography = world.state.domain(GeographyState)
    projection = project_world(geography, seed=world.state.meta.seed)

    assert projection.city_id == geography.seed_city_id
    assert len(projection.buildings) == len(geography.buildings)
    assert projection.report["placement"]["unplaced"] == 0
    assert len(connected_components(projection.streets)) == 1
    assert len(projection.transit_lines) >= 2
    assert projection.bounds.width > 0.0 and projection.bounds.height > 0.0


def test_projecting_hydra_does_not_touch_the_world(world):
    before = world.state.state_hash()
    project_world(world.state.domain(GeographyState), seed=world.state.meta.seed)
    assert world.state.state_hash() == before


def test_a_fork_of_a_world_keeps_the_same_city(world):
    """Two timelines of one world must look identical: the layout is not history."""

    geography = world.state.domain(GeographyState)
    seed = world.state.meta.seed
    assert content_digest(project_world(geography, seed=seed)) == content_digest(
        project_world(geography, seed=seed)
    )


def test_projection_is_fast_enough_to_be_free(world):
    """It runs once per world, off the tick loop -- but it still cannot take minutes."""

    projection = project_world(world.state.domain(GeographyState), seed=world.state.meta.seed)
    assert float(projection.report["total_ms"]) < 8_000.0


def test_no_simulation_system_imports_the_projection_engine():
    """The engine reads the world. If a system ever read the engine, that would invert.

    Spatial layout must never become an input to the simulation: the moment a system
    consults it, the world stops being reproducible from its own seed and rules alone.
    """

    root = Path(__file__).resolve().parent.parent / "packages"
    offenders = []
    for path in sorted(root.rglob("hydra/**/*.py")):
        if "spatial" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "hydra.spatial" in text:
            offenders.append(str(path.relative_to(root)))
    assert offenders == [], f"simulation code imports the projection engine: {offenders}"
