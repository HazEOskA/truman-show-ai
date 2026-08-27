"""View model: presence, frames, layers and the wire form.

Two promises are load-bearing here and both are asserted below.

*Honesty*: every drawn position says whether the world stated it or the view inferred it,
and the inference has exactly one rule. A City View that quietly invents positions is a
second simulation wearing the first one's clothes.

*Cheapness*: frames are built by the worker, in the same process that advances time. If
building one ever costs more than a slice of a tick, the city's appearance starts slowing
the city down, and the simulation is the thing that matters.
"""

from __future__ import annotations

import gzip
import json
import time

import pytest

from hydra.agents.model import Activity, AgentsState, Employment, Person, Sex, Tier
from hydra.geography.model import GeographyState
from hydra.kernel.clock import TICKS_PER_HOUR
from hydra.spatial import project_world
from hydra.viewmodel import (
    build_delta,
    build_index,
    build_keyframe,
    apply_delta,
    compute_layers,
    frame_from_dict,
    layer_catalogue,
    presence_of,
    projection_payload,
    resolve_all,
)
from hydra.viewmodel.layers import LAYERS, LayerScope
from hydra.viewmodel.presence import PresenceSource, is_working_hour


def person(**overrides) -> Person:
    base = dict(
        person_id="p1",
        name="Test Person",
        tier=Tier.LIGHTWEIGHT,
        sex=Sex.F,
        birth_tick=0,
        age_years=34.0,
        district_id="d1",
        home_building_id="home",
        work_building_id="work",
        employment=Employment.EMPLOYED,
        activity=Activity.ACTIVE,
    )
    base.update(overrides)
    return Person(**base)


# -- presence: the one override ---------------------------------------------------

NOON = 12 * TICKS_PER_HOUR
NIGHT = 2 * TICKS_PER_HOUR


def test_a_recorded_location_is_reported_as_observed():
    p = person(location_building_id="somewhere_else")
    result = presence_of(p, NOON)
    assert result.building_id == "somewhere_else"
    assert result.source is PresenceSource.OBSERVED


def test_a_worker_stuck_at_home_mid_shift_is_shown_at_work_and_labelled():
    """The stale-location override, the only inference the view is allowed to make."""

    p = person(location_building_id="home")
    result = presence_of(p, NOON)
    assert result.building_id == "work"
    assert result.source is PresenceSource.DERIVED


def test_the_override_does_not_fire_outside_working_hours():
    p = person(location_building_id="home")
    result = presence_of(p, NIGHT)
    assert result.building_id == "home"
    assert result.source is PresenceSource.OBSERVED


def test_the_override_does_not_fire_for_someone_asleep():
    p = person(location_building_id="home", activity=Activity.SLEEP)
    result = presence_of(p, NOON)
    assert result.building_id == "home"
    assert result.source is PresenceSource.OBSERVED


def test_the_override_does_not_fire_for_someone_with_no_job():
    p = person(location_building_id="home", employment=Employment.RETIRED, work_building_id="")
    result = presence_of(p, NOON)
    assert result.building_id == "home"
    assert result.source is PresenceSource.OBSERVED


def test_a_location_that_is_neither_home_nor_work_is_always_trusted():
    """That location came from an action the person actually took."""

    p = person(location_building_id="the_hospital")
    assert presence_of(p, NOON).source is PresenceSource.OBSERVED
    assert presence_of(p, NIGHT).source is PresenceSource.OBSERVED


def test_a_person_with_no_location_at_all_is_inferred():
    p = person(location_building_id="")
    assert presence_of(p, NOON).building_id == "work"
    assert presence_of(p, NOON).source is PresenceSource.DERIVED
    assert presence_of(p, NIGHT).building_id == "home"


def test_a_person_with_nowhere_to_be_is_not_drawn():
    p = person(location_building_id="", home_building_id="", work_building_id="")
    result = presence_of(p, NOON)
    assert result.building_id == ""
    assert result.source is PresenceSource.UNKNOWN


def test_working_hours_are_the_working_day():
    assert not is_working_hour(NIGHT)
    assert is_working_hour(NOON)
    assert not is_working_hour(22 * TICKS_PER_HOUR)


# -- frames -----------------------------------------------------------------------


@pytest.fixture
def daytime(world):
    while world.state.meta.tick < 14 * TICKS_PER_HOUR:
        world.kernel.tick()
    return world


def test_a_keyframe_holds_every_living_person(daytime):
    agents = daytime.state.domain(AgentsState)
    frame = build_keyframe(daytime.state)
    assert len(frame.agents) == len(agents.alive_people())
    assert frame.kind == "keyframe"
    assert frame.presence.total == len(frame.agents)


def test_the_view_says_how_much_of_the_crowd_is_inferred(daytime):
    """Hydra does not simulate the commute, and the City View must not pretend it does."""

    frame = build_keyframe(daytime.state)
    report = frame.presence.as_dict()
    assert report["derived"] > 0, "at 2pm most workers are still recorded at home"
    assert report["observed"] > 0
    assert 0.0 < report["observed_share"] < 1.0


def test_a_delta_carries_only_what_moved(daytime):
    index = build_index(daytime.state.domain(GeographyState))
    keyframe = build_keyframe(daytime.state, index)
    daytime.kernel.tick()
    delta = build_delta(daytime.state, keyframe, index)
    assert delta.kind == "delta"
    assert len(delta.agents) < len(keyframe.agents)


def test_a_keyframe_plus_its_deltas_equals_the_keyframe_you_would_have_built(daytime):
    """If this drifts, viewers slowly stop seeing the world the world is in."""

    index = build_index(daytime.state.domain(GeographyState))
    accumulated = build_keyframe(daytime.state, index)
    for _ in range(8):
        daytime.kernel.tick()
        accumulated = apply_delta(accumulated, build_delta(daytime.state, accumulated, index))

    fresh = build_keyframe(daytime.state, index)
    assert accumulated.agents == fresh.agents
    assert accumulated.buildings == fresh.buildings
    assert accumulated.districts == fresh.districts


def test_a_frame_survives_the_wire(daytime):
    frame = build_keyframe(daytime.state)
    restored = frame_from_dict(json.loads(json.dumps(frame.as_dict())))
    assert restored.agents == frame.agents
    assert restored.buildings == frame.buildings
    assert restored.districts == frame.districts
    assert restored.tick == frame.tick


def test_frames_stay_small_enough_to_stream(daytime):
    index = build_index(daytime.state.domain(GeographyState))
    keyframe = build_keyframe(daytime.state, index)
    key_bytes = len(gzip.compress(json.dumps(keyframe.as_dict(), separators=(",", ":")).encode()))
    assert key_bytes < 400_000, "a keyframe must stay downloadable"

    accumulated = keyframe
    worst = 0
    for _ in range(6):
        daytime.kernel.tick()
        delta = build_delta(daytime.state, accumulated, index)
        payload = json.dumps(delta.as_dict(), separators=(",", ":")).encode()
        worst = max(worst, len(gzip.compress(payload)))
        accumulated = apply_delta(accumulated, delta)
    assert worst < 20_000, f"deltas must stay small; worst was {worst} bytes"


def test_building_a_frame_does_not_cost_the_simulation_a_tick(daytime):
    """The budget that protects the project.

    Frames are built inside the worker's loop. The whole point of the delta stream is that
    watching the city is nearly free; if this assertion ever fails, the City View has begun
    charging the simulation for its own appearance.
    """

    index = build_index(daytime.state.domain(GeographyState))
    keyframe = build_keyframe(daytime.state, index)

    samples = []
    for _ in range(5):
        started = time.perf_counter()
        build_delta(daytime.state, keyframe, index)
        samples.append(time.perf_counter() - started)
    median = sorted(samples)[len(samples) // 2]
    assert median < 0.060, f"delta build took {median * 1000:.1f} ms"


def test_a_frame_never_touches_the_world(daytime):
    before = daytime.state.state_hash()
    index = build_index(daytime.state.domain(GeographyState))
    keyframe = build_keyframe(daytime.state, index)
    build_delta(daytime.state, keyframe, index)
    compute_layers(daytime.state)
    assert daytime.state.state_hash() == before


# -- layers -----------------------------------------------------------------------


def test_every_layer_reads_a_real_number_from_the_world(world):
    values = compute_layers(world.state)
    assert len(values) == len(LAYERS)
    for layer in LAYERS:
        got = values[layer.layer_id]
        assert got, f"{layer.layer_id} produced nothing"
        assert all(isinstance(v, float) for v in got.values())


def test_district_layers_cover_every_district_and_building_layers_every_building(world):
    geography = world.state.domain(GeographyState)
    district_ids = set(geography.city().district_ids)
    values = compute_layers(world.state)
    for layer in LAYERS:
        keys = set(values[layer.layer_id])
        if layer.scope is LayerScope.DISTRICT:
            assert keys == district_ids, f"{layer.layer_id} misses districts"
        else:
            assert keys == set(geography.buildings), f"{layer.layer_id} misses buildings"


def test_the_catalogue_tells_the_viewer_where_each_number_came_from():
    catalogue = layer_catalogue()
    assert len(catalogue) == len(LAYERS)
    for entry in catalogue:
        assert entry["source"], f"{entry['id']} does not say what it reads"
        assert entry["high"] > entry["low"]


def test_asking_for_one_layer_computes_only_that_layer(world):
    values = compute_layers(world.state, ("wealth",))
    assert list(values) == ["wealth"]


# -- the wire form ----------------------------------------------------------------


def test_the_projection_payload_is_small_enough_to_download(world):
    geography = world.state.domain(GeographyState)
    index = build_index(geography)
    projection = project_world(geography, seed=world.state.meta.seed)
    payload = projection_payload(projection, index)
    packed = gzip.compress(json.dumps(payload, separators=(",", ":")).encode())
    assert len(packed) < 400_000, f"projection payload was {len(packed)} bytes gzipped"


def test_the_payload_and_the_frames_agree_on_the_order_of_things(world):
    """Worker and API never speak; they agree by both sorting. Prove they still do."""

    geography = world.state.domain(GeographyState)
    index = build_index(geography)
    projection = project_world(geography, seed=world.state.meta.seed)
    payload = projection_payload(projection, index)
    assert payload["order"]["buildings"] == index.buildings
    assert payload["order"]["districts"] == index.districts

    frame = build_keyframe(world.state, index)
    for _, row in frame.agents.items():
        assert -1 <= row[0] < len(index.buildings)


def test_every_placed_building_has_geometry_in_the_payload(world):
    geography = world.state.domain(GeographyState)
    index = build_index(geography)
    projection = project_world(geography, seed=world.state.meta.seed)
    payload = projection_payload(projection, index)
    rects = payload["buildings"]["rect"]
    assert len(rects) == len(index.buildings) * 5
    widths = rects[2::5]
    assert all(w > 0 for w in widths), "a building with no width was never placed"


def test_resolve_all_agrees_with_the_frame(daytime):
    presences, report = resolve_all(daytime.state.domain(AgentsState), daytime.state.meta.tick)
    frame = build_keyframe(daytime.state)
    assert len(presences) == len(frame.agents)
    assert report.as_dict() == frame.presence.as_dict()
