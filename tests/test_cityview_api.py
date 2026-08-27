"""City View API, exercised over HTTP against a real world.

These run the actual FastAPI app against a world created on disk, so they catch the things
unit tests on the view model cannot: a router that never got registered, a field the read
model assumed and the domain never had, a panel that 500s on the one building with no owner.
"""

from __future__ import annotations

import json

import pytest

from hydra.agents.model import AgentsState
from hydra.geography.model import GeographyState

fastapi_testclient = pytest.importorskip("fastapi.testclient")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """A live API over a small world, run to mid-afternoon of its first day.

    The worker owns time, so the fixture plays its part: it builds the world against the
    service's own store, ticks it to a busy hour, and publishes the live state exactly as
    the worker would. The API then reads it the way it reads any running world.
    """

    import os

    data_dir = tmp_path_factory.mktemp("cityview-data")
    os.environ["HYDRA_DATA_DIR"] = str(data_dir)
    os.environ.pop("HYDRA_DATABASE_URL", None)
    os.environ.pop("HYDRA_REDIS_URL", None)

    from hydra.kernel.clock import TICKS_PER_HOUR
    from hydra.kernel.config import WorldConfig
    from hydra.persistence.store import ControlState
    from hydra.world import create_world
    from hydra_api.main import app, service

    config = WorldConfig(world_name="Hydra City Test")
    config.population.total_residents = 2_000
    config.population.lightweight_agents = 200
    config.population.persistent_agents = 12
    config.economy.company_count = 30

    runtime = create_world(config, seed=4242, world_id="world_city", store=service.store)
    while runtime.state.meta.tick < 14 * TICKS_PER_HOUR:
        runtime.kernel.tick()
    runtime.ledger.flush()
    service.store.write_live(runtime.kernel.snapshot())
    service.store.put_control(
        ControlState(world_id="world_city", timeline_id="tl_zero", mode="paused", speed=4.0)
    )
    service.invalidate("tl_zero")

    with fastapi_testclient.TestClient(app) as http:
        yield http, "tl_zero"


def test_the_projection_downloads(client):
    http, timeline_id = client
    response = http.get(f"/city/{timeline_id}/projection")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["projection_hash"]
    assert payload["bounds"]["max_x"] > payload["bounds"]["min_x"]
    assert len(payload["districts"]) == 8
    assert payload["order"]["buildings"], "the shared ordering must be published"
    assert len(payload["buildings"]["rect"]) == len(payload["order"]["buildings"]) * 5
    assert payload["streets"]["a"], "a city with no streets is a scatter plot"
    assert payload["street_names"], "streets are named so buildings can have addresses"


def test_the_projection_is_the_same_city_every_time(client):
    http, timeline_id = client
    first = http.get(f"/city/{timeline_id}/projection").json()
    second = http.get(f"/city/{timeline_id}/projection").json()
    assert first["projection_hash"] == second["projection_hash"]
    assert first["buildings"]["rect"] == second["buildings"]["rect"]


def test_the_keyframe_describes_the_population(client):
    http, timeline_id = client
    payload = http.get(f"/city/{timeline_id}/keyframe").json()
    assert payload["kind"] == "keyframe"
    assert payload["agents"]["id"], "a city with nobody in it is not a city"
    assert len(payload["agents"]["b"]) == len(payload["agents"]["id"])
    assert payload["presence"]["observed"] + payload["presence"]["derived"] > 0
    assert payload["codes"]["source"] == ["observed", "derived", "unknown"]


def test_agent_positions_point_at_real_buildings(client):
    http, timeline_id = client
    projection = http.get(f"/city/{timeline_id}/projection").json()
    frame = http.get(f"/city/{timeline_id}/keyframe").json()
    count = len(projection["order"]["buildings"])
    for position in frame["agents"]["b"]:
        assert -1 <= position < count


def test_the_layer_catalogue_is_served(client):
    http, _ = client
    payload = http.get("/city/layers").json()
    ids = {entry["id"] for entry in payload["layers"]}
    assert {"wealth", "pollution", "crime", "sleep", "occupancy"} <= ids
    for entry in payload["layers"]:
        assert entry["source"]


def test_layer_values_come_back_for_the_requested_layers(client):
    http, timeline_id = client
    payload = http.get(f"/city/{timeline_id}/layers", params={"ids": "wealth,crime"}).json()
    assert set(payload["values"]) == {"wealth", "crime"}
    assert payload["values"]["wealth"], "wealth is a real district field"


def test_clicking_a_building_opens_a_panel(client):
    http, timeline_id = client
    projection = http.get(f"/city/{timeline_id}/projection").json()
    building_id = projection["order"]["buildings"][0]

    payload = http.get(f"/city/{timeline_id}/building/{building_id}").json()
    assert payload["building_id"] == building_id
    assert payload["kind"]
    assert payload["district"]["id"]
    assert "people_here_total" in payload
    assert payload["people_here_total"] >= payload["observed_here"]


def test_a_missing_building_is_a_404_not_a_guess(client):
    http, timeline_id = client
    assert http.get(f"/city/{timeline_id}/building/building_nope").status_code == 404


def test_clicking_a_person_opens_a_panel_that_says_how_it_knows(client):
    http, timeline_id = client
    frame = http.get(f"/city/{timeline_id}/keyframe").json()
    person_id = frame["agents"]["id"][0]

    payload = http.get(f"/city/{timeline_id}/agent/{person_id}").json()
    assert payload["person_id"] == person_id
    assert payload["name"]
    assert payload["position"]["source"] in ("observed", "derived", "unknown")
    assert "awake" in payload
    assert payload["home"] is None or payload["home"]["building_id"]


def test_events_are_anchored_honestly(client):
    http, timeline_id = client
    payload = http.get(f"/city/{timeline_id}/events", params={"limit": 40}).json()
    for event in payload["events"]:
        assert event["anchor_kind"] in ("building", "district", "none")
        if event["anchor_kind"] == "none":
            assert event["anchor"] is None
        else:
            assert event["anchor"] and len(event["anchor"]) == 2
        assert event["topic"]


def test_a_missing_world_is_a_404(client):
    http, _ = client
    assert http.get("/city/tl_does_not_exist/keyframe").status_code == 404


def test_a_stream_opens_with_a_keyframe_then_sends_deltas(client):
    """A viewer must be able to draw the city from the very first message they receive."""

    from hydra_api.cityview import FrameStream
    from hydra_api.main import service

    _, timeline_id = client
    state = service.state(timeline_id)
    feed = FrameStream(timeline_id, resync_every=0)

    first = feed.next_frame(state)
    assert first is not None and first.kind == "keyframe"
    assert first.agents

    assert feed.next_frame(state) is None, "an unchanged world sends nothing"

    state.meta.tick += 1
    second = feed.next_frame(state)
    assert second is not None and second.kind == "delta"
    state.meta.tick -= 1


def test_a_stream_resends_a_keyframe_so_viewers_cannot_drift(client):
    from hydra_api.cityview import FrameStream
    from hydra_api.main import service

    _, timeline_id = client
    state = service.state(timeline_id)
    feed = FrameStream(timeline_id, resync_every=2)

    assert feed.next_frame(state).kind == "keyframe"
    state.meta.tick += 1
    assert feed.next_frame(state).kind == "delta"
    state.meta.tick += 1
    assert feed.next_frame(state).kind == "keyframe"
    state.meta.tick -= 2
