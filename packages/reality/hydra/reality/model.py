"""Core contracts for Hydra Reality Engine.

v0.1 introduced deterministic material batches and finite transformations.
v0.2 adds continuous state transitions driven by environment and resources while
keeping the original process contracts backwards compatible.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


_EPSILON = 1e-9


class ProcessStatus(str, enum.Enum):
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETE = "complete"


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
    to zero. This is enough to model temperature, water and sunlight response
    curves without embedding species-specific code in the engine.
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
    provenance: dict[str, ProvenanceEvent] = field(default_factory=dict)
    environment: dict[str, float] = field(default_factory=dict)
    next_batch_index: int = 0
    next_process_index: int = 0
    next_event_index: int = 0
