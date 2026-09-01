"""Core contracts for Hydra Reality Engine.

v0.1 introduced deterministic material batches and finite transformations.
v0.2 added continuous state transitions driven by environment and resources.
v0.3 adds spatial natural fields, seasonal forcing and renewable/depletable
stocks without changing the earlier process contracts.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field


_EPSILON = 1e-9


class ProcessStatus(str, enum.Enum):
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETE = "complete"


class FieldKind(str, enum.Enum):
    FOREST = "forest"
    FARMLAND = "farmland"
    AQUIFER = "aquifer"
    DEPOSIT = "deposit"
    WETLAND = "wetland"
    GRASSLAND = "grassland"


@dataclass(frozen=True, slots=True)
class ResourceDefinition:
    code: str
    unit: str
    category: str = "material"


@dataclass(slots=True)
class ResourceBatch:
    batch_id: str
    resource_code: str
    quantity: float
    unit: str
    created_minute: int
    provenance_event_id: str
    parent_batch_ids: tuple[str, ...] = ()

    def take(self, quantity: float) -> float:
        if quantity < -_EPSILON:
            raise ValueError("quantity must be non-negative")
        amount = min(self.quantity, quantity)
        self.quantity -= amount
        if abs(self.quantity) < _EPSILON:
            self.quantity = 0.0
        return amount


@dataclass(slots=True)
class Location:
    location_id: str
    name: str = ""
    inventory: dict[str, list[ResourceBatch]] = field(default_factory=dict)
    environment: dict[str, float] = field(default_factory=dict)
    state_variables: dict[str, float] = field(default_factory=dict)

    def quantity(self, resource_code: str) -> float:
        return sum(batch.quantity for batch in self.inventory.get(resource_code, ()))

    def add(self, batch: ResourceBatch) -> None:
        self.inventory.setdefault(batch.resource_code, []).append(batch)

    def consume(self, resource_code: str, quantity: float) -> list[tuple[ResourceBatch, float]]:
        if quantity < -_EPSILON:
            raise ValueError("quantity must be non-negative")
        available = self.quantity(resource_code)
        if available + _EPSILON < quantity:
            raise ValueError(
                f"{self.location_id} has {available:.6f} {resource_code}, needs {quantity:.6f}"
            )
        remaining = quantity
        consumed: list[tuple[ResourceBatch, float]] = []
        for batch in self.inventory.get(resource_code, ()):
            if remaining <= _EPSILON:
                break
            amount = batch.take(remaining)
            if amount > _EPSILON:
                consumed.append((batch, amount))
                remaining -= amount
        self.inventory[resource_code] = [
            batch for batch in self.inventory.get(resource_code, ()) if batch.quantity > _EPSILON
        ]
        return consumed


@dataclass(frozen=True, slots=True)
class Condition:
    metric: str
    minimum: float | None = None
    maximum: float | None = None

    def accepts(self, environment: dict[str, float]) -> bool:
        value = environment.get(self.metric)
        if value is None:
            return False
        if self.minimum is not None and value < self.minimum:
            return False
        if self.maximum is not None and value > self.maximum:
            return False
        return True


@dataclass(frozen=True, slots=True)
class RateModifier:
    """Piecewise-linear environmental multiplier.

    Outside ``minimum..maximum`` the rate is zero. Between minimum and the
    optimum band it rises linearly to 1; after the optimum band it falls back
    to zero. Species and process-specific response curves therefore remain
    data, not hard-coded engine branches.
    """

    metric: str
    minimum: float
    optimum_min: float
    optimum_max: float
    maximum: float

    def __post_init__(self) -> None:
        if not self.minimum <= self.optimum_min <= self.optimum_max <= self.maximum:
            raise ValueError("rate modifier bounds must be ordered")

    def factor(self, environment: dict[str, float]) -> float:
        value = environment.get(self.metric)
        if value is None or value <= self.minimum or value >= self.maximum:
            return 0.0
        if self.optimum_min <= value <= self.optimum_max:
            return 1.0
        if value < self.optimum_min:
            span = self.optimum_min - self.minimum
            return 1.0 if span <= _EPSILON else (value - self.minimum) / span
        span = self.maximum - self.optimum_max
        return 1.0 if span <= _EPSILON else (self.maximum - value) / span


@dataclass(frozen=True, slots=True)
class SeasonalSignal:
    """Deterministic periodic environmental forcing.

    A signal can represent daylight, temperature tendency, rainfall tendency
    or any other smooth annual/diurnal driver. More realistic weather can
    later layer stochastic-but-seeded events on top of the same metric.
    """

    metric: str
    mean: float
    amplitude: float
    period_days: float = 365.0
    phase_day: float = 0.0
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        if self.period_days <= 0:
            raise ValueError("period_days must be positive")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("seasonal signal minimum cannot exceed maximum")

    def value_at(self, minute: float) -> float:
        day = minute / 1440.0
        angle = 2.0 * math.pi * ((day - self.phase_day) / self.period_days)
        value = self.mean + self.amplitude * math.sin(angle)
        if self.minimum is not None:
            value = max(self.minimum, value)
        if self.maximum is not None:
            value = min(self.maximum, value)
        return value


@dataclass(frozen=True, slots=True)
class FieldRule:
    """One rate equation applied to a stock inside a natural field.

    Positive rates replenish/grow a stock; negative rates drain/degrade it.
    Rules can consume or produce other field stocks per unit of change. When
    ``logistic`` is enabled, positive growth slows as the stock approaches its
    maximum, giving forests/crops carrying-capacity behaviour without a
    species-specific engine implementation.
    """

    code: str
    stock_metric: str
    base_rate_per_day: float
    minimum_value: float = 0.0
    maximum_value: float | None = None
    conditions: tuple[Condition, ...] = ()
    rate_modifiers: tuple[RateModifier, ...] = ()
    input_stocks_per_unit: dict[str, float] = field(default_factory=dict)
    output_stocks_per_unit: dict[str, float] = field(default_factory=dict)
    logistic: bool = False

    def __post_init__(self) -> None:
        if abs(self.base_rate_per_day) <= _EPSILON:
            raise ValueError("field rule base_rate_per_day cannot be zero")
        if self.maximum_value is not None and self.maximum_value < self.minimum_value:
            raise ValueError("field rule maximum cannot be below minimum")
        if self.logistic and (self.maximum_value is None or self.base_rate_per_day < 0):
            raise ValueError("logistic field rule requires positive growth and a maximum")
        for mapping in (self.input_stocks_per_unit, self.output_stocks_per_unit):
            if any(quantity < 0 for quantity in mapping.values()):
                raise ValueError("field coupling quantities must be non-negative")


@dataclass(slots=True)
class NaturalField:
    """Spatially anchored natural capital.

    Stocks here are not inventory batches. They are physical state still in
    the world: standing forest biomass, soil water, groundwater or ore in the
    ground. Material enters inventory only through explicit field extraction.
    """

    field_id: str
    kind: FieldKind
    location_id: str
    area_hectares: float
    stocks: dict[str, float]
    stock_units: dict[str, str]
    extractable_as: dict[str, str] = field(default_factory=dict)
    rules: tuple[FieldRule, ...] = ()
    environment: dict[str, float] = field(default_factory=dict)
    resolution_minutes: int = 1440
    last_updated_minute: int = 0
    active: bool = True

    def __post_init__(self) -> None:
        if self.area_hectares <= 0:
            raise ValueError("field area_hectares must be positive")
        if self.resolution_minutes <= 0:
            raise ValueError("field resolution_minutes must be positive")
        if any(value < -_EPSILON for value in self.stocks.values()):
            raise ValueError("field stocks must be non-negative")
        missing_units = set(self.stocks) - set(self.stock_units)
        if missing_units:
            raise ValueError(f"field stocks missing units: {sorted(missing_units)}")
        unknown_extractable = set(self.extractable_as) - set(self.stocks)
        if unknown_extractable:
            raise ValueError(f"extractable field stocks not defined: {sorted(unknown_extractable)}")

    def quantity(self, metric: str) -> float:
        return self.stocks.get(metric, 0.0)


@dataclass(frozen=True, slots=True)
class ProcessDefinition:
    code: str
    duration_minutes: int
    inputs: dict[str, float]
    outputs: dict[str, float]
    byproducts: dict[str, float] = field(default_factory=dict)
    conditions: tuple[Condition, ...] = ()
    equipment_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive")
        if not self.outputs and not self.byproducts:
            raise ValueError("a process must produce at least one output")
        for mapping in (self.inputs, self.outputs, self.byproducts):
            if any(quantity < 0 for quantity in mapping.values()):
                raise ValueError("resource quantities must be non-negative")


@dataclass(frozen=True, slots=True)
class ContinuousProcessDefinition:
    """A state transition whose rate depends on the current world.

    ``state_metric`` can be biomass, temperature, charge, cure fraction,
    hydration, cooking progress, wear, healing or any other scalar state.
    ``inputs_per_progress`` are consumed proportionally to actual progress, so
    a slowed process does not magically use full-speed resources.
    """

    code: str
    state_metric: str
    initial_value: float
    target_value: float
    base_rate_per_minute: float
    inputs_per_progress: dict[str, float] = field(default_factory=dict)
    outputs: dict[str, float] = field(default_factory=dict)
    byproducts: dict[str, float] = field(default_factory=dict)
    conditions: tuple[Condition, ...] = ()
    rate_modifiers: tuple[RateModifier, ...] = ()

    def __post_init__(self) -> None:
        if abs(self.target_value - self.initial_value) <= _EPSILON:
            raise ValueError("continuous process target must differ from initial value")
        if self.base_rate_per_minute <= 0:
            raise ValueError("base_rate_per_minute must be positive")
        for mapping in (self.inputs_per_progress, self.outputs, self.byproducts):
            if any(quantity < 0 for quantity in mapping.values()):
                raise ValueError("resource quantities must be non-negative")


@dataclass(frozen=True, slots=True)
class ConsumedResource:
    resource_code: str
    quantity: float
    batch_id: str
    provenance_event_id: str


@dataclass(slots=True)
class ProcessInstance:
    process_id: str
    definition_code: str
    input_location_id: str
    output_location_id: str
    started_minute: int
    elapsed_minutes: int = 0
    status: ProcessStatus = ProcessStatus.RUNNING
    consumed: tuple[ConsumedResource, ...] = ()
    note: str = ""


@dataclass(slots=True)
class ContinuousProcessInstance:
    process_id: str
    definition_code: str
    location_id: str
    output_location_id: str
    started_minute: int
    value: float
    elapsed_minutes: int = 0
    status: ProcessStatus = ProcessStatus.RUNNING
    consumed: list[ConsumedResource] = field(default_factory=list)
    note: str = ""


@dataclass(frozen=True, slots=True)
class ProvenanceEvent:
    event_id: str
    kind: str
    minute: int
    process_id: str
    resource_code: str
    quantity: float
    output_batch_id: str
    input_batch_ids: tuple[str, ...] = ()
    source: str = ""


@dataclass(slots=True)
class RealityState:
    minute: int = 0
    resources: dict[str, ResourceDefinition] = field(default_factory=dict)
    locations: dict[str, Location] = field(default_factory=dict)
    processes: dict[str, ProcessDefinition] = field(default_factory=dict)
    continuous_processes: dict[str, ContinuousProcessDefinition] = field(default_factory=dict)
    running: dict[str, ProcessInstance] = field(default_factory=dict)
    continuous_running: dict[str, ContinuousProcessInstance] = field(default_factory=dict)
    fields: dict[str, NaturalField] = field(default_factory=dict)
    seasonal_signals: dict[str, SeasonalSignal] = field(default_factory=dict)
    provenance: dict[str, ProvenanceEvent] = field(default_factory=dict)
    environment: dict[str, float] = field(default_factory=dict)
    next_batch_index: int = 0
    next_process_index: int = 0
    next_event_index: int = 0
