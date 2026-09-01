"""Acceptance tests for Hydra Reality Engine v0.2 continuous processes."""

from __future__ import annotations

import pytest

from hydra.reality import (
    Condition,
    ContinuousProcessDefinition,
    ProcessStatus,
    RateModifier,
    RealityEngine,
    ResourceDefinition,
)


def test_tree_growth_responds_to_environment_and_resumes_after_drought() -> None:
    engine = RealityEngine()
    engine.register_resource(ResourceDefinition("water", "kg", "natural"))
    engine.register_resource(ResourceDefinition("standing_timber", "kg", "natural"))
    engine.add_location("forest")

    engine.seed_resource("forest", "water", 10.0, source="genesis:aquifer_001")
    engine.set_environment("temperature_c", 22.0, location_id="forest")
    engine.set_environment("sunlight", 1.0, location_id="forest")
    engine.set_environment("soil_moisture", 0.8, location_id="forest")

    engine.register_continuous_process(
        ContinuousProcessDefinition(
            code="grow_tree",
            state_metric="tree_biomass_kg",
            initial_value=0.0,
            target_value=10.0,
            base_rate_per_minute=0.01,
            inputs_per_progress={"water": 0.5},
            outputs={"standing_timber": 10.0},
            conditions=(Condition("soil_moisture", minimum=0.3),),
            rate_modifiers=(
                RateModifier("temperature_c", 5.0, 20.0, 25.0, 40.0),
                RateModifier("sunlight", 0.0, 0.8, 1.2, 1.5),
            ),
        )
    )

    process = engine.start_continuous("grow_tree", location_id="forest")
    engine.advance(500)

    assert process.status is ProcessStatus.RUNNING
    assert process.value == pytest.approx(5.0)
    assert engine.state.locations["forest"].quantity("water") == pytest.approx(7.5)

    engine.set_environment("soil_moisture", 0.1, location_id="forest")
    engine.advance(100)
    assert process.status is ProcessStatus.BLOCKED
    assert process.value == pytest.approx(5.0)
    assert engine.state.locations["forest"].quantity("water") == pytest.approx(7.5)

    engine.set_environment("soil_moisture", 0.8, location_id="forest")
    engine.advance(500)

    assert process.status is ProcessStatus.COMPLETE
    assert process.value == pytest.approx(10.0)
    assert engine.state.locations["forest"].quantity("water") == pytest.approx(5.0)
    assert engine.state.locations["forest"].quantity("standing_timber") == pytest.approx(10.0)
    assert engine.state.minute == 1100

    timber = engine.state.locations["forest"].inventory["standing_timber"][0]
    chain = engine.provenance_chain(timber.batch_id)
    assert "genesis:aquifer_001" in {event.source for event in chain if event.kind == "origin"}


def test_heating_then_boiling_potato_uses_state_from_previous_process() -> None:
    engine = RealityEngine()
    for code, unit, category in (
        ("electricity", "kWh", "energy"),
        ("raw_potato", "unit", "food"),
        ("cooked_potato", "unit", "food"),
    ):
        engine.register_resource(ResourceDefinition(code, unit, category))

    engine.add_location("kitchen")
    engine.seed_resource("kitchen", "electricity", 2.0, source="genesis:grid")
    engine.seed_resource("kitchen", "raw_potato", 1.0, source="genesis:field_001")

    engine.register_continuous_process(
        ContinuousProcessDefinition(
            code="heat_water",
            state_metric="water_temperature_c",
            initial_value=20.0,
            target_value=100.0,
            base_rate_per_minute=2.0,
            inputs_per_progress={"electricity": 0.01},
        )
    )
    engine.register_continuous_process(
        ContinuousProcessDefinition(
            code="boil_potato",
            state_metric="potato_cook_fraction",
            initial_value=0.0,
            target_value=1.0,
            base_rate_per_minute=1.0 / 30.0,
            inputs_per_progress={"raw_potato": 1.0},
            outputs={"cooked_potato": 1.0},
            conditions=(Condition("water_temperature_c", minimum=95.0),),
        )
    )

    heating = engine.start_continuous("heat_water", location_id="kitchen")
    engine.advance(40)

    assert heating.status is ProcessStatus.COMPLETE
    assert engine.state.locations["kitchen"].state_variables["water_temperature_c"] == pytest.approx(100.0)
    assert engine.state.locations["kitchen"].quantity("electricity") == pytest.approx(1.2)

    cooking = engine.start_continuous("boil_potato", location_id="kitchen")
    engine.advance(30)

    assert cooking.status is ProcessStatus.COMPLETE
    assert engine.state.locations["kitchen"].state_variables["potato_cook_fraction"] == pytest.approx(1.0)
    assert engine.state.locations["kitchen"].quantity("raw_potato") == pytest.approx(0.0)
    assert engine.state.locations["kitchen"].quantity("cooked_potato") == pytest.approx(1.0)
    assert engine.state.minute == 70

    cooked = engine.state.locations["kitchen"].inventory["cooked_potato"][0]
    chain = engine.provenance_chain(cooked.batch_id)
    assert "genesis:field_001" in {event.source for event in chain if event.kind == "origin"}


def test_cooking_blocks_below_boiling_temperature_and_cooling_runs_downward() -> None:
    engine = RealityEngine()
    engine.register_resource(ResourceDefinition("raw_potato", "unit", "food"))
    engine.register_resource(ResourceDefinition("cooked_potato", "unit", "food"))
    engine.add_location("kitchen")
    engine.seed_resource("kitchen", "raw_potato", 1.0, source="genesis:field_002")
    engine.set_state_variable("kitchen", "water_temperature_c", 90.0)

    engine.register_continuous_process(
        ContinuousProcessDefinition(
            code="boil_potato",
            state_metric="potato_cook_fraction",
            initial_value=0.0,
            target_value=1.0,
            base_rate_per_minute=1.0 / 30.0,
            inputs_per_progress={"raw_potato": 1.0},
            outputs={"cooked_potato": 1.0},
            conditions=(Condition("water_temperature_c", minimum=95.0),),
        )
    )

    cooking = engine.start_continuous("boil_potato", location_id="kitchen")
    engine.advance(30)
    assert cooking.status is ProcessStatus.BLOCKED
    assert cooking.value == pytest.approx(0.0)
    assert engine.state.locations["kitchen"].quantity("raw_potato") == pytest.approx(1.0)

    engine.set_state_variable("kitchen", "water_temperature_c", 100.0)
    engine.advance(30)
    assert cooking.status is ProcessStatus.COMPLETE
    assert engine.state.locations["kitchen"].quantity("cooked_potato") == pytest.approx(1.0)

    engine.register_continuous_process(
        ContinuousProcessDefinition(
            code="cool_water",
            state_metric="water_temperature_c",
            initial_value=100.0,
            target_value=20.0,
            base_rate_per_minute=1.0,
        )
    )
    cooling = engine.start_continuous("cool_water", location_id="kitchen")
    engine.advance(80)

    assert cooling.status is ProcessStatus.COMPLETE
    assert engine.state.locations["kitchen"].state_variables["water_temperature_c"] == pytest.approx(20.0)
