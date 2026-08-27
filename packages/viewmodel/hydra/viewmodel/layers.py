"""The data layers a viewer can switch on over the city.

Every layer here reads a number the simulation already maintains. None of them computes
anything the world does not know: a layer is a lens on state, and if the value is not in
state there is no layer, because a coloured map of an invented quantity is a lie told in
a convincing format.

Each layer declares its scope (districts or buildings), where its value comes from, and the
range it should be normalised against for colour. The range matters: auto-scaling every
layer to its own min and max makes a calm city look as alarming as a burning one.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Callable

from hydra.agents.model import Activity, AgentsState
from hydra.geography.model import GeographyState
from hydra.kernel.state import WorldState


class LayerScope(str, enum.Enum):
    DISTRICT = "district"
    BUILDING = "building"


@dataclass(frozen=True, slots=True)
class Layer:
    layer_id: str
    label: str
    scope: LayerScope
    #: What the number means, shown in the legend.
    unit: str
    #: Normalisation range for colour. Values outside are clamped, not rescaled.
    low: float
    high: float
    #: True when a high value is bad, so the palette runs the other way.
    high_is_bad: bool
    source: str
    compute: Callable[[WorldState], dict[str, float]]


# -- district layers --------------------------------------------------------------


def _districts(state: WorldState):
    geography = state.domain(GeographyState)
    return geography, geography.city_districts(geography.seed_city_id)


def _wealth(state: WorldState) -> dict[str, float]:
    _, districts = _districts(state)
    return {d.district_id: d.wealth_index for d in districts}


def _pollution(state: WorldState) -> dict[str, float]:
    _, districts = _districts(state)
    return {d.district_id: d.pollution for d in districts}


def _crime(state: WorldState) -> dict[str, float]:
    _, districts = _districts(state)
    return {d.district_id: d.crime_rate for d in districts}


def _unrest(state: WorldState) -> dict[str, float]:
    _, districts = _districts(state)
    return {d.district_id: d.unrest for d in districts}


def _density(state: WorldState) -> dict[str, float]:
    _, districts = _districts(state)
    return {d.district_id: d.population / max(0.01, d.area_km2) for d in districts}


def _power_reliability(state: WorldState) -> dict[str, float]:
    _, districts = _districts(state)
    return {d.district_id: d.power_reliability for d in districts}


def _transport_load(state: WorldState) -> dict[str, float]:
    _, districts = _districts(state)
    return {d.district_id: d.transport_load / max(0.01, d.transport_capacity) for d in districts}


def _land_value(state: WorldState) -> dict[str, float]:
    _, districts = _districts(state)
    return {d.district_id: d.land_value_minor / 100.0 for d in districts}


def _service_coverage(state: WorldState) -> dict[str, float]:
    _, districts = _districts(state)
    out = {}
    for d in districts:
        values = list(d.service_coverage.values())
        out[d.district_id] = sum(values) / len(values) if values else 0.0
    return out


def _employment(state: WorldState) -> dict[str, float]:
    """Employed share, individuals and cohorts together, weighted by head count."""

    agents = state.domain(AgentsState)
    _, districts = _districts(state)
    employed: dict[str, float] = {d.district_id: 0.0 for d in districts}
    workforce: dict[str, float] = {d.district_id: 0.0 for d in districts}
    for person in agents.people.values():
        if not person.alive or person.district_id not in workforce:
            continue
        workforce[person.district_id] += 1.0
        if person.employer_id:
            employed[person.district_id] += 1.0
    for cohort in agents.cohorts.values():
        if cohort.district_id not in workforce:
            continue
        workforce[cohort.district_id] += cohort.size
        employed[cohort.district_id] += cohort.size * cohort.employment_rate
    return {k: employed[k] / workforce[k] if workforce[k] else 0.0 for k in workforce}


def _asleep(state: WorldState) -> dict[str, float]:
    """Share of the district's individuals who are asleep or dormant right now."""

    agents = state.domain(AgentsState)
    _, districts = _districts(state)
    asleep: dict[str, float] = {d.district_id: 0.0 for d in districts}
    total: dict[str, float] = {d.district_id: 0.0 for d in districts}
    for person in agents.people.values():
        if not person.alive or person.district_id not in total:
            continue
        total[person.district_id] += 1.0
        if person.activity in (Activity.SLEEP, Activity.DORMANT):
            asleep[person.district_id] += 1.0
    return {k: asleep[k] / total[k] if total[k] else 0.0 for k in total}


def _sentiment(state: WorldState) -> dict[str, float]:
    return _cohort_mean(state, "sentiment")


def _trust(state: WorldState) -> dict[str, float]:
    return _cohort_mean(state, "trust_government")


def _health(state: WorldState) -> dict[str, float]:
    return _cohort_mean(state, "health")


def _awareness(state: WorldState) -> dict[str, float]:
    """How widely the district has heard the thing most people have heard about."""

    agents = state.domain(AgentsState)
    _, districts = _districts(state)
    out: dict[str, float] = {d.district_id: 0.0 for d in districts}
    weight: dict[str, float] = {d.district_id: 0.0 for d in districts}
    for cohort in agents.cohorts.values():
        if cohort.district_id not in out:
            continue
        peak = max(cohort.awareness.values(), default=0.0)
        out[cohort.district_id] += peak * cohort.size
        weight[cohort.district_id] += cohort.size
    return {k: out[k] / weight[k] if weight[k] else 0.0 for k in out}


def _cohort_mean(state: WorldState, field: str) -> dict[str, float]:
    agents = state.domain(AgentsState)
    _, districts = _districts(state)
    totals: dict[str, float] = {d.district_id: 0.0 for d in districts}
    sizes: dict[str, float] = {d.district_id: 0.0 for d in districts}
    for cohort in agents.cohorts.values():
        if cohort.district_id not in totals:
            continue
        totals[cohort.district_id] += getattr(cohort, field) * cohort.size
        sizes[cohort.district_id] += cohort.size
    return {k: totals[k] / sizes[k] if sizes[k] else 0.0 for k in totals}


# -- building layers --------------------------------------------------------------


def _occupancy(state: WorldState) -> dict[str, float]:
    geography = state.domain(GeographyState)
    return {
        b.building_id: b.occupancy / b.capacity if b.capacity else 0.0
        for b in geography.buildings.values()
    }


def _condition(state: WorldState) -> dict[str, float]:
    geography = state.domain(GeographyState)
    return {b.building_id: b.condition for b in geography.buildings.values()}


LAYERS: tuple[Layer, ...] = (
    Layer("wealth", "Wealth", LayerScope.DISTRICT, "index", 0.0, 1.0, False,
          "district.wealth_index", _wealth),
    Layer("land_value", "Land value", LayerScope.DISTRICT, "per m2", 0.0, 400.0, False,
          "district.land_value_minor", _land_value),
    Layer("density", "Population density", LayerScope.DISTRICT, "people/km2", 0.0, 2000.0, False,
          "district.population / area_km2", _density),
    Layer("employment", "Employment", LayerScope.DISTRICT, "share", 0.4, 1.0, False,
          "agents + cohorts", _employment),
    Layer("pollution", "Pollution", LayerScope.DISTRICT, "index", 0.0, 1.0, True,
          "district.pollution", _pollution),
    Layer("crime", "Crime", LayerScope.DISTRICT, "rate", 0.0, 0.20, True,
          "district.crime_rate", _crime),
    Layer("unrest", "Unrest", LayerScope.DISTRICT, "index", 0.0, 0.5, True,
          "district.unrest", _unrest),
    Layer("power", "Power reliability", LayerScope.DISTRICT, "share", 0.5, 1.0, False,
          "district.power_reliability", _power_reliability),
    Layer("transport", "Transport load", LayerScope.DISTRICT, "of capacity", 0.0, 1.5, True,
          "district.transport_load / transport_capacity", _transport_load),
    Layer("services", "Service coverage", LayerScope.DISTRICT, "share", 0.0, 1.0, False,
          "district.service_coverage", _service_coverage),
    Layer("sleep", "Asleep now", LayerScope.DISTRICT, "share", 0.0, 1.0, False,
          "person.activity", _asleep),
    Layer("sentiment", "Sentiment", LayerScope.DISTRICT, "index", 0.2, 0.8, False,
          "cohort.sentiment", _sentiment),
    Layer("trust", "Trust in government", LayerScope.DISTRICT, "index", 0.0, 1.0, False,
          "cohort.trust_government", _trust),
    Layer("health", "Health", LayerScope.DISTRICT, "index", 0.5, 1.0, False,
          "cohort.health", _health),
    Layer("awareness", "Awareness", LayerScope.DISTRICT, "share", 0.0, 1.0, False,
          "cohort.awareness", _awareness),
    Layer("occupancy", "Building occupancy", LayerScope.BUILDING, "of capacity", 0.0, 1.0, False,
          "building.occupancy / capacity", _occupancy),
    Layer("condition", "Building condition", LayerScope.BUILDING, "index", 0.3, 1.0, False,
          "building.condition", _condition),
)

LAYER_BY_ID: dict[str, Layer] = {layer.layer_id: layer for layer in LAYERS}


def layer_catalogue() -> list[dict[str, object]]:
    """What the layer switcher shows, including where each number comes from."""

    return [
        {
            "id": layer.layer_id,
            "label": layer.label,
            "scope": layer.scope.value,
            "unit": layer.unit,
            "low": layer.low,
            "high": layer.high,
            "high_is_bad": layer.high_is_bad,
            "source": layer.source,
        }
        for layer in LAYERS
    ]


def compute_layers(state: WorldState, layer_ids: tuple[str, ...] = ()) -> dict[str, dict[str, float]]:
    """Values for the requested layers, or all of them. Rounded for the wire."""

    wanted = [LAYER_BY_ID[i] for i in layer_ids if i in LAYER_BY_ID] or list(LAYERS)
    return {
        layer.layer_id: {k: round(v, 5) for k, v in sorted(layer.compute(state).items())}
        for layer in wanted
    }
