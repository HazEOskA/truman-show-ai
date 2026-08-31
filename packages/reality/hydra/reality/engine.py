"""Deterministic material/process engine for Hydra Reality Engine v0.1."""

from __future__ import annotations

from .model import (
    ConsumedResource,
    Location,
    ProcessDefinition,
    ProcessInstance,
    ProcessStatus,
    ProvenanceEvent,
    RealityState,
    ResourceBatch,
    ResourceDefinition,
)


class RealityEngine:
    """Owns material transitions. No output exists without an explicit source or process."""

    def __init__(self, state: RealityState | None = None) -> None:
        self.state = state or RealityState()

    def register_resource(self, definition: ResourceDefinition) -> None:
        current = self.state.resources.get(definition.code)
        if current is not None and current != definition:
            raise ValueError(f"resource already registered differently: {definition.code}")
        self.state.resources[definition.code] = definition

    def add_location(self, location_id: str, *, name: str = "") -> Location:
        if location_id in self.state.locations:
            raise ValueError(f"location already exists: {location_id}")
        location = Location(location_id=location_id, name=name)
        self.state.locations[location_id] = location
        return location

    def register_process(self, definition: ProcessDefinition) -> None:
        if definition.code in self.state.processes:
            raise ValueError(f"process already exists: {definition.code}")
        unknown = (
            set(definition.inputs) | set(definition.outputs) | set(definition.byproducts)
        ) - set(self.state.resources)
        if unknown:
            raise ValueError(f"process {definition.code} uses unknown resources: {sorted(unknown)}")
        self.state.processes[definition.code] = definition

    def seed_resource(
        self,
        location_id: str,
        resource_code: str,
        quantity: float,
        *,
        source: str,
    ) -> ResourceBatch:
        """Create explicit Genesis/natural stock with an auditable origin."""

        if not source.strip():
            raise ValueError("seed_resource requires a non-empty source")
        if quantity <= 0:
            raise ValueError("seed quantity must be positive")
        resource = self._resource(resource_code)
        location = self._location(location_id)
        batch_id = self._next_batch_id()
        event_id = self._next_event_id()
        batch = ResourceBatch(
            batch_id=batch_id,
            resource_code=resource_code,
            quantity=float(quantity),
            unit=resource.unit,
            created_minute=self.state.minute,
            provenance_event_id=event_id,
        )
        location.add(batch)
        self.state.provenance[event_id] = ProvenanceEvent(
            event_id=event_id,
            kind="origin",
            minute=self.state.minute,
            process_id="",
            resource_code=resource_code,
            quantity=float(quantity),
            output_batch_id=batch_id,
            source=source,
        )
        return batch

    def start(
        self,
        definition_code: str,
        *,
        input_location_id: str,
        output_location_id: str | None = None,
    ) -> ProcessInstance:
        definition = self.state.processes[definition_code]
        source = self._location(input_location_id)
        destination = self._location(output_location_id or input_location_id)

        missing_conditions = [
            condition.metric
            for condition in definition.conditions
            if not condition.accepts(self.state.environment)
        ]
        if missing_conditions:
            raise ValueError(
                f"conditions not satisfied for {definition_code}: {sorted(missing_conditions)}"
            )

        # Validate all inputs first so start is atomic.
        for resource_code, quantity in definition.inputs.items():
            available = source.quantity(resource_code)
            if available + 1e-9 < quantity:
                raise ValueError(
                    f"insufficient {resource_code} at {source.location_id}: "
                    f"{available:.6f} < {quantity:.6f}"
                )

        consumed: list[ConsumedResource] = []
        for resource_code, quantity in definition.inputs.items():
            for batch, amount in source.consume(resource_code, quantity):
                consumed.append(
                    ConsumedResource(
                        resource_code=resource_code,
                        quantity=amount,
                        batch_id=batch.batch_id,
                        provenance_event_id=batch.provenance_event_id,
                    )
                )

        self.state.next_process_index += 1
        process_id = f"proc_{self.state.next_process_index:08d}"
        instance = ProcessInstance(
            process_id=process_id,
            definition_code=definition.code,
            input_location_id=source.location_id,
            output_location_id=destination.location_id,
            started_minute=self.state.minute,
            consumed=tuple(consumed),
        )
        self.state.running[process_id] = instance
        return instance

    def advance(self, minutes: int) -> None:
        if minutes < 0:
            raise ValueError("minutes must be non-negative")
        target = self.state.minute + minutes

        while True:
            completion_times: list[tuple[int, str]] = []
            for process_id, instance in self.state.running.items():
                if instance.status is not ProcessStatus.RUNNING:
                    continue
                definition = self.state.processes[instance.definition_code]
                remaining = definition.duration_minutes - instance.elapsed_minutes
                completion_times.append((self.state.minute + max(0, remaining), process_id))
            if not completion_times:
                break

            next_minute, process_id = min(completion_times)
            if next_minute > target:
                break
            delta = next_minute - self.state.minute
            self._progress_all(delta)
            self.state.minute = next_minute
            self._finish(self.state.running[process_id])

        tail = target - self.state.minute
        self._progress_all(tail)
        self.state.minute = target

    def provenance_chain(self, batch_id: str) -> list[ProvenanceEvent]:
        """Return all causal material events for a batch, oldest first."""

        by_batch = {event.output_batch_id: event for event in self.state.provenance.values()}
        ordered: list[ProvenanceEvent] = []
        seen: set[str] = set()

        def visit(current_batch_id: str) -> None:
            event = by_batch.get(current_batch_id)
            if event is None or event.event_id in seen:
                return
            for parent in event.input_batch_ids:
                visit(parent)
            seen.add(event.event_id)
            ordered.append(event)

        visit(batch_id)
        return ordered

    def _progress_all(self, delta: int) -> None:
        if delta <= 0:
            return
        for instance in self.state.running.values():
            if instance.status is not ProcessStatus.RUNNING:
                continue
            definition = self.state.processes[instance.definition_code]
            if all(condition.accepts(self.state.environment) for condition in definition.conditions):
                instance.elapsed_minutes = min(
                    definition.duration_minutes,
                    instance.elapsed_minutes + delta,
                )
            else:
                instance.status = ProcessStatus.BLOCKED
                instance.note = "environment condition failed"

    def _finish(self, instance: ProcessInstance) -> None:
        if instance.status is not ProcessStatus.RUNNING:
            return
        definition = self.state.processes[instance.definition_code]
        if instance.elapsed_minutes < definition.duration_minutes:
            return

        destination = self._location(instance.output_location_id)
        parent_batch_ids = tuple(sorted({entry.batch_id for entry in instance.consumed}))
        products = list(definition.outputs.items()) + list(definition.byproducts.items())
        for resource_code, quantity in products:
            if quantity <= 0:
                continue
            resource = self._resource(resource_code)
            batch_id = self._next_batch_id()
            event_id = self._next_event_id()
            batch = ResourceBatch(
                batch_id=batch_id,
                resource_code=resource_code,
                quantity=float(quantity),
                unit=resource.unit,
                created_minute=self.state.minute,
                provenance_event_id=event_id,
                parent_batch_ids=parent_batch_ids,
            )
            destination.add(batch)
            self.state.provenance[event_id] = ProvenanceEvent(
                event_id=event_id,
                kind="process",
                minute=self.state.minute,
                process_id=instance.process_id,
                resource_code=resource_code,
                quantity=float(quantity),
                output_batch_id=batch_id,
                input_batch_ids=parent_batch_ids,
            )
        instance.status = ProcessStatus.COMPLETE
        instance.note = "complete"

    def _resource(self, code: str) -> ResourceDefinition:
        try:
            return self.state.resources[code]
        except KeyError as exc:
            raise KeyError(f"unknown resource: {code}") from exc

    def _location(self, location_id: str) -> Location:
        try:
            return self.state.locations[location_id]
        except KeyError as exc:
            raise KeyError(f"unknown location: {location_id}") from exc

    def _next_batch_id(self) -> str:
        self.state.next_batch_index += 1
        return f"batch_{self.state.next_batch_index:08d}"

    def _next_event_id(self) -> str:
        self.state.next_event_index += 1
        return f"reality_{self.state.next_event_index:08d}"
