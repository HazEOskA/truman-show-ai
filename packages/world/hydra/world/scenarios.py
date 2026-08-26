"""Operator scenarios.

A scenario is a controlled perturbation of the physical world — a plant losing output, a
supply route cut, a subsidy forced through. It changes an initial condition and then lets the
world react on its own. Scenarios never write a storyline: no scenario touches prices,
employment, opinion or events downstream of the thing it perturbs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from hydra.events.importance import ImportanceInputs
from hydra.events.model import Topics, Visibility
from hydra.geography.model import GeographyState
from hydra.kernel.context import TickContext

from .builder import WorldRuntime


@dataclass(slots=True)
class ScenarioResult:
    name: str
    tick: int
    event_id: str
    detail: dict[str, Any]


def _context(runtime: WorldRuntime) -> TickContext:
    return runtime.kernel.ctx


def plant_failure(runtime: WorldRuntime, *, plant_id: str = "plant_kelvar", loss: float = 0.4) -> ScenarioResult:
    """A generating unit loses part of its output. Everything after this is the world's doing."""

    ctx = _context(runtime)
    geography = ctx.state.domain(GeographyState)
    plant = geography.power_plants.get(plant_id)
    if plant is None:
        raise KeyError(f"unknown power plant {plant_id}")
    before = plant.availability
    plant.availability = round(max(0.0, plant.availability * (1.0 - loss)), 4)
    lost_mw = round(plant.capacity_mw * (before - plant.availability), 3)
    building = geography.buildings.get(plant.building_id)
    if building is not None:
        building.condition = round(max(0.1, building.condition - loss * 0.5), 4)

    event = ctx.emit(
        Topics.ENV_INCIDENT,
        "plant_output_loss",
        actor=plant_id,
        location=building.district_id if building else geography.seed_city_id,
        payload={
            "plant": plant_id,
            "fuel": plant.fuel,
            "loss_share": loss,
            "lost_mw": lost_mw,
            "availability": plant.availability,
        },
        inputs=ImportanceInputs(
            people_affected=sum(d.population for d in geography.districts.values()) * 0.6,
            economic_impact=lost_mw * 1000 * 24 * 40,
            political_impact=0.7,
            risk=0.65,
            novelty=0.9,
        ),
        visibility=Visibility.PUBLIC,
    )
    runtime.kernel.bus.drain()
    return ScenarioResult(
        name="plant_failure",
        tick=ctx.tick,
        event_id=event.event_id,
        detail={"plant": plant_id, "lost_mw": lost_mw, "availability": plant.availability},
    )


def plant_repair(runtime: WorldRuntime, *, plant_id: str = "plant_kelvar", recover: float = 1.0) -> ScenarioResult:
    ctx = _context(runtime)
    geography = ctx.state.domain(GeographyState)
    plant = geography.power_plants[plant_id]
    plant.availability = round(min(1.0, plant.availability + (1.0 - plant.availability) * recover), 4)
    event = ctx.emit(
        Topics.ENV_INCIDENT,
        "plant_repaired",
        actor=plant_id,
        payload={"plant": plant_id, "availability": plant.availability},
        importance=0.5,
    )
    runtime.kernel.bus.drain()
    return ScenarioResult(name="plant_repair", tick=ctx.tick, event_id=event.event_id,
                          detail={"availability": plant.availability})


def cold_snap(runtime: WorldRuntime, *, drop_c: float = 12.0) -> ScenarioResult:
    """A weather shock: heating demand rises, and the grid has to find the power."""

    ctx = _context(runtime)
    geography = ctx.state.domain(GeographyState)
    geography.weather.temperature_c = round(geography.weather.temperature_c - drop_c, 3)
    geography.weather.cold_stress = round(max(0.0, (2.0 - geography.weather.temperature_c) / 16.0), 4)
    event = ctx.emit(
        Topics.ENV_WEATHER,
        "cold_snap",
        location=geography.seed_city_id,
        payload={"temperature_c": geography.weather.temperature_c, "drop_c": drop_c},
        inputs=ImportanceInputs(
            people_affected=sum(d.population for d in geography.districts.values()),
            risk=0.5,
            political_impact=0.3,
            novelty=0.7,
        ),
    )
    runtime.kernel.bus.drain()
    return ScenarioResult(name="cold_snap", tick=ctx.tick, event_id=event.event_id,
                          detail={"temperature_c": geography.weather.temperature_c})


def supply_shock(runtime: WorldRuntime, *, code: str = "materials", loss: float = 0.5) -> ScenarioResult:
    """A trade route closes: local stock of one good is destroyed or stranded."""

    from hydra.economy.model import EconomyState

    ctx = _context(runtime)
    economy = ctx.state.domain(EconomyState)
    market = economy.markets[code]
    removed = round(market.inventory * loss, 3)
    market.inventory = round(market.inventory - removed, 3)
    event = ctx.emit(
        Topics.MARKET_SHORTAGE,
        "supply_shock",
        target=code,
        payload={"code": code, "removed": removed, "remaining": market.inventory},
        inputs=ImportanceInputs(
            people_affected=20_000,
            economic_impact=removed * market.price_minor,
            political_impact=0.35,
            risk=0.4,
            novelty=0.8,
        ),
    )
    runtime.kernel.bus.drain()
    return ScenarioResult(name="supply_shock", tick=ctx.tick, event_id=event.event_id,
                          detail={"code": code, "removed": removed})


SCENARIOS: dict[str, Callable[..., ScenarioResult]] = {
    "plant_failure": plant_failure,
    "plant_repair": plant_repair,
    "cold_snap": cold_snap,
    "supply_shock": supply_shock,
}


def run_scenario(runtime: WorldRuntime, name: str, **params: Any) -> ScenarioResult:
    scenario = SCENARIOS.get(name)
    if scenario is None:
        raise KeyError(f"unknown scenario {name!r}; available: {', '.join(sorted(SCENARIOS))}")
    return scenario(runtime, **params)
