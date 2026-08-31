"""Acceptance tests for Hydra Reality Engine v0.3 natural fields and cycles."""

from __future__ import annotations

import pytest

from hydra.reality import (
    Condition,
    FieldKind,
    FieldRule,
    NaturalField,
    RateModifier,
    RealityEngine,
    ResourceDefinition,
    SeasonalSignal,
)


def test_forest_grows_stalls_in_drought_recovers_and_extracts_real_stock() -> None:
    engine = RealityEngine()
    engine.register_resource(ResourceDefinition("standing_timber", "kg", "natural"))
    engine.add_location("forest_edge")

    engine.set_environment("temperature_c", 22.0, location_id="forest_edge")
    engine.set_environment("sunlight", 1.0, location_id="forest_edge")
    engine.set_environment("rainfall_factor", 0.0, location_id="forest_edge")

    forest = engine.add_field(
        NaturalField(
            field_id="forest_001",
            kind=FieldKind.FOREST,
            location_id="forest_edge",
            area_hectares=25.0,
            stocks={
                "biomass_kg": 100.0,
                "soil_water_l": 200.0,
                "soil_nutrients_kg": 10.0,
            },
            stock_units={
                "biomass_kg": "kg",
                "soil_water_l": "L",
                "soil_nutrients_kg": "kg",
            },
            extractable_as={"biomass_kg": "standing_timber"},
            resolution_minutes=1440,
            rules=(
                FieldRule(
                    code="01_rain_recharge",
                    stock_metric="soil_water_l",
                    base_rate_per_day=300.0,
                    maximum_value=1000.0,
                    rate_modifiers=(
                        RateModifier("rainfall_factor", 0.0, 0.8, 1.2, 2.0),
                    ),
                ),
                FieldRule(
                    code="02_forest_growth",
                    stock_metric="biomass_kg",
                    base_rate_per_day=100.0,
                    maximum_value=1000.0,
                    logistic=True,
                    conditions=(Condition("soil_water_l", minimum=100.0),),
                    rate_modifiers=(
                        RateModifier("temperature_c", 5.0, 20.0, 25.0, 40.0),
                        RateModifier("sunlight", 0.0, 0.8, 1.2, 1.5),
                    ),
                    input_stocks_per_unit={
                        "soil_water_l": 2.0,
                        "soil_nutrients_kg": 0.01,
                    },
                ),
                FieldRule(
                    code="03_evaporation",
                    stock_metric="soil_water_l",
                    base_rate_per_day=-50.0,
                    minimum_value=0.0,
                ),
            ),
        )
    )

    # Dry day: the forest grows once using stored soil water, then the soil dries out.
    engine.advance(1440)
    assert forest.quantity("biomass_kg") == pytest.approx(190.0)
    assert forest.quantity("soil_water_l") == pytest.approx(0.0)
    assert forest.quantity("soil_nutrients_kg") == pytest.approx(9.1)

    # Second dry day: water condition blocks biomass growth.
    engine.advance(1440)
    assert forest.quantity("biomass_kg") == pytest.approx(190.0)
    assert forest.quantity("soil_water_l") == pytest.approx(0.0)

    # Rain returns. Recharge runs first, growth resumes, then evaporation removes water.
    engine.set_environment("rainfall_factor", 1.0, location_id="forest_edge")
    engine.advance(1440)
    assert forest.quantity("biomass_kg") == pytest.approx(271.0)
    assert forest.quantity("soil_water_l") == pytest.approx(88.0)
    assert forest.quantity("soil_nutrients_kg") == pytest.approx(8.29)

    # Natural stock becomes inventory only through explicit timed extraction.
    timber = engine.extract_from_field(
        "forest_001",
        "biomass_kg",
        100.0,
        duration_minutes=60,
    )
    assert forest.quantity("biomass_kg") == pytest.approx(171.0)
    assert engine.state.locations["forest_edge"].quantity("standing_timber") == pytest.approx(100.0)
    assert engine.state.minute == 3 * 1440 + 60

    chain = engine.provenance_chain(timber.batch_id)
    assert len(chain) == 1
    assert chain[0].kind == "field_extraction"
    assert chain[0].source == "field:forest_001:biomass_kg"


def test_finite_mineral_deposit_depletes_and_does_not_regenerate_by_magic() -> None:
    engine = RealityEngine()
    engine.register_resource(ResourceDefinition("iron_ore", "kg", "material"))
    engine.add_location("mine_entrance")

    deposit = engine.add_field(
        NaturalField(
            field_id="iron_deposit_001",
            kind=FieldKind.DEPOSIT,
            location_id="mine_entrance",
            area_hectares=8.0,
            stocks={"iron_ore_kg": 1000.0},
            stock_units={"iron_ore_kg": "kg"},
            extractable_as={"iron_ore_kg": "iron_ore"},
            rules=(),
        )
    )

    ore = engine.extract_from_field(
        "iron_deposit_001",
        "iron_ore_kg",
        100.0,
        duration_minutes=60,
    )
    assert deposit.quantity("iron_ore_kg") == pytest.approx(900.0)
    assert engine.state.locations["mine_entrance"].quantity("iron_ore") == pytest.approx(100.0)

    engine.advance(365 * 1440)
    assert deposit.quantity("iron_ore_kg") == pytest.approx(900.0)

    chain = engine.provenance_chain(ore.batch_id)
    assert chain[0].source == "field:iron_deposit_001:iron_ore_kg"


def test_seasonal_signal_is_deterministic_and_explicit_weather_can_override_it() -> None:
    engine = RealityEngine()
    engine.add_location("valley")
    engine.register_seasonal_signal(
        SeasonalSignal(
            metric="temperature_c",
            mean=10.0,
            amplitude=10.0,
            period_days=4.0,
            phase_day=0.0,
            minimum=0.0,
            maximum=20.0,
        )
    )

    assert engine.environment_at("valley")["temperature_c"] == pytest.approx(10.0)

    engine.advance(1440)
    assert engine.environment_at("valley")["temperature_c"] == pytest.approx(20.0)

    engine.advance(2 * 1440)
    assert engine.environment_at("valley")["temperature_c"] == pytest.approx(0.0)

    # Weather/event systems can override the seasonal baseline without changing the clock.
    engine.set_environment("temperature_c", 7.0, location_id="valley")
    assert engine.environment_at("valley")["temperature_c"] == pytest.approx(7.0)
