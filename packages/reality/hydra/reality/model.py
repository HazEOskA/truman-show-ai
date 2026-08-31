"""Core contracts for Hydra Reality Engine v0.1.

The reality layer is deliberately independent from the existing Hydra kernel in v0.1.
It models material state and deterministic processes so it can later be mounted as a
kernel domain without changing the contracts.
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
    running: dict[str, ProcessInstance] = field(default_factory=dict)
    provenance: dict[str, ProvenanceEvent] = field(default_factory=dict)
    environment: dict[str, float] = field(default_factory=dict)
    next_batch_index: int = 0
    next_process_index: int = 0
    next_event_index: int = 0
