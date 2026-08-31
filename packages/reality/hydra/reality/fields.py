"""Spatial substrate and natural cycles for Hydra Reality Engine v0.3.

A field cell is a piece of physical world, not scenery. It owns finite stocks such as
forest biomass, soil water, crop biomass or ore. Natural cycles mutate those stocks over
simulated time; extraction is the only bridge from a field stock into material inventory.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .model import RateModifier, ResourceBatch

if TYPE_CHECKING:
    from .engine import RealityEngine as BaseRealityEngine

_EPSILON = 1e-9
_MINUTES_PER_DAY = 1440.0


@dataclass(frozen=True, slots=True)
class LinearDriver:
    """Turn one environmental metric into a multiplicative activity factor."""

    metric: str
    scale: float = 1.0
    offset: float = 0.0
    minimum_factor: float = 0.0
    maximum_factor: float = 1000.0

    def factor(self, environment: dict[str, float]) -> float:
        value = environment.get(self.metric)
        if value is None:
            return 0.0
        raw = (value - self.offset) * self.scale
        return min(self.maximum_factor, max(self.minimum_factor, raw))


@dataclass(frozen=True, slots=True)
class SeasonalCurve:
    """Deterministic annual forcing, e.g. growing season or solar availability."""

    minimum_factor: float = 0.0
    maximum_factor: float = 1.0
    peak_day: float = 172.0
    period_days: float = 365.0

    def __post_init__(self) -> None:
        if self.period_days <= 0:
            raise ValueError("period_days must be positive")
        if self.minimum_factor < 0 or self.maximum_factor < self.minimum_factor:
            raise ValueError("invalid seasonal factor bounds")

    def factor(self, day_of_year: float) -> float:
        midpoint = (self.maximum_factor + self.minimum_factor) / 2.0
        amplitude = (self.maximum_factor - self.minimum_factor) / 2.0
        angle = 2.0 * math.pi * (day_of_year - self.peak_day) / self.period_days
        return midpoint + amplitude * math.cos(angle)


@dataclass(slots=True)
class FieldCell:
    cell_id: str
    location_id: str
    area_km2: float
    biome: str
    stocks: dict[str, float] = field(default_factory=dict)
    capacities: dict[str, float] = field(default_factory=dict)
    environment: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.area_km2 <= 0:
            raise ValueError("field area_km2 must be positive")
        if any(value < 0 for value in self.stocks.values()):
            raise ValueError("field stocks cannot be negative")
        if any(value < 0 for value in self.capacities.values()):
            raise ValueError("field capacities cannot be negative")

    def stock(self, code: str) -> float:
        return self.stocks.get(code, 0.0)


@dataclass(frozen=True, slots=True)
class NaturalCycleDefinition:
    """Generic rule that changes one stock and optional coupled stocks over time.

    ``base_rate_per_day`` is signed: positive grows/recharges, negative depletes/evaporates.
    ``coflows_per_unit`` are applied per absolute unit of actual target-stock movement. This
    lets 1 kg of biomass growth consume soil water/nutrients without species-specific code.
    """

    code: str
    target_stock: str
    base_rate_per_day: float
    minimum: float = 0.0
    maximum: float | None = None
    coflows_per_unit: dict[str, float] = field(default_factory=dict)
    rate_modifiers: tuple[RateModifier, ...] = ()
    linear_drivers: tuple[LinearDriver, ...] = ()
    seasonal: SeasonalCurve | None = None

    def __post_init__(self) -> None:
        if abs(self.base_rate_per_day) <= _EPSILON:
            raise ValueError("natural cycle rate cannot be zero")
        if self.maximum is not None and self.maximum < self.minimum:
            raise ValueError("natural cycle maximum must be >= minimum")


@dataclass(slots=True)
class NaturalWorldState:
    cells: dict[str, FieldCell] = field(default_factory=dict)
    cycles: dict[str, NaturalCycleDefinition] = field(default_factory=dict)
    active_cycles: dict[str, list[str]] = field(default_factory=dict)
    extracted: dict[str, float] = field(default_factory=dict)


class NaturalWorld:
    """Field-level physical world driven by the same simulated clock as RealityEngine."""

    def __init__(
        self,
        reality: BaseRealityEngine,
        state: NaturalWorldState | None = None,
    ) -> None:
        self.reality = reality
        self.state = state or NaturalWorldState()

    def add_cell(self, cell: FieldCell) -> FieldCell:
        if cell.cell_id in self.state.cells:
            raise ValueError(f"field cell already exists: {cell.cell_id}")
        if cell.location_id not in self.reality.state.locations:
            raise KeyError(f"field location does not exist: {cell.location_id}")
        self.state.cells[cell.cell_id] = cell
        self.state.active_cycles.setdefault(cell.cell_id, [])
        return cell

    def register_cycle(self, definition: NaturalCycleDefinition) -> None:
        if definition.code in self.state.cycles:
            raise ValueError(f"natural cycle already exists: {definition.code}")
        self.state.cycles[definition.code] = definition

    def activate(self, cell_id: str, cycle_code: str) -> None:
        self._cell(cell_id)
        if cycle_code not in self.state.cycles:
            raise KeyError(f"unknown natural cycle: {cycle_code}")
        active = self.state.active_cycles.setdefault(cell_id, [])
        if cycle_code not in active:
            active.append(cycle_code)

    def set_environment(self, cell_id: str, metric: str, value: float) -> None:
        self._cell(cell_id).environment[metric] = float(value)

    def environment_at(self, cell_id: str) -> dict[str, float]:
        cell = self._cell(cell_id)
        merged = self.reality.environment_at(cell.location_id)
        merged.update(cell.environment)
        merged.update(cell.stocks)
        return merged

    def advance(self, minutes: int, *, start_minute: int) -> None:
        """Advance natural fields deterministically, splitting at day boundaries."""

        if minutes < 0:
            raise ValueError("minutes must be non-negative")
        elapsed = 0
        while elapsed < minutes:
            absolute_minute = start_minute + elapsed
            minute_in_day = absolute_minute % int(_MINUTES_PER_DAY)
            until_day_boundary = int(_MINUTES_PER_DAY) - minute_in_day
            delta = min(minutes - elapsed, until_day_boundary)
            self._advance_slice(delta, absolute_minute)
            elapsed += delta

    def extract(
        self,
        cell_id: str,
        stock_code: str,
        quantity: float,
        *,
        resource_code: str,
        to_location_id: str | None = None,
    ) -> ResourceBatch:
        """Move finite field stock into auditable material inventory."""

        if quantity <= 0:
            raise ValueError("extraction quantity must be positive")
        cell = self._cell(cell_id)
        available = cell.stock(stock_code)
        if available + _EPSILON < quantity:
            raise ValueError(
                f"insufficient {stock_code} in {cell_id}: {available:.6f} < {quantity:.6f}"
            )
        cell.stocks[stock_code] = max(0.0, available - quantity)
        key = f"{cell_id}:{stock_code}"
        self.state.extracted[key] = self.state.extracted.get(key, 0.0) + quantity
        return self.reality.seed_resource(
            to_location_id or cell.location_id,
            resource_code,
            quantity,
            source=f"field:{cell_id}:{stock_code}",
        )

    def _advance_slice(self, minutes: int, absolute_minute: int) -> None:
        if minutes <= 0:
            return
        days = minutes / _MINUTES_PER_DAY
        day_of_year = (absolute_minute / _MINUTES_PER_DAY) % 365.0
        for cell_id, cycle_codes in self.state.active_cycles.items():
            cell = self.state.cells[cell_id]
            for cycle_code in cycle_codes:
                definition = self.state.cycles[cycle_code]
                self._apply_cycle(cell, definition, days, day_of_year)

    def _apply_cycle(
        self,
        cell: FieldCell,
        definition: NaturalCycleDefinition,
        days: float,
        day_of_year: float,
    ) -> None:
        environment = self.environment_at(cell.cell_id)
        factor = 1.0
        for modifier in definition.rate_modifiers:
            factor *= modifier.factor(environment)
        for driver in definition.linear_drivers:
            factor *= driver.factor(environment)
        if definition.seasonal is not None:
            factor *= definition.seasonal.factor(day_of_year)
        if factor <= _EPSILON:
            return

        current = cell.stock(definition.target_stock)
        requested = definition.base_rate_per_day * factor * days
        lower = definition.minimum
        upper = definition.maximum
        if upper is None:
            upper = cell.capacities.get(definition.target_stock, math.inf)
        next_value = min(upper, max(lower, current + requested))
        actual = next_value - current
        if abs(actual) <= _EPSILON:
            return

        # Coupled stocks can limit the primary cycle. Negative coflows consume stock.
        magnitude = abs(actual)
        scale = 1.0
        for stock_code, per_unit in definition.coflows_per_unit.items():
            if per_unit >= 0 or abs(per_unit) <= _EPSILON:
                continue
            available = cell.stock(stock_code)
            needed = abs(per_unit) * magnitude
            if needed > _EPSILON:
                scale = min(scale, available / needed)
        actual *= max(0.0, min(1.0, scale))
        magnitude = abs(actual)
        if magnitude <= _EPSILON:
            return

        cell.stocks[definition.target_stock] = current + actual
        for stock_code, per_unit in definition.coflows_per_unit.items():
            updated = cell.stock(stock_code) + per_unit * magnitude
            capacity = cell.capacities.get(stock_code, math.inf)
            cell.stocks[stock_code] = min(capacity, max(0.0, updated))

    def _cell(self, cell_id: str) -> FieldCell:
        try:
            return self.state.cells[cell_id]
        except KeyError as exc:
            raise KeyError(f"unknown field cell: {cell_id}") from exc
