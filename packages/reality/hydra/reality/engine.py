"""Deterministic physical/process engine for Hydra Reality Engine v0.1-v0.3."""

from __future__ import annotations

import math

from .model import (
    ConsumedResource,
    ContinuousProcessDefinition,
    ContinuousProcessInstance,
    Location,
    NaturalField,
    ProcessDefinition,
    ProcessInstance,
    ProcessStatus,
    ProvenanceEvent,
    RealityState,
    ResourceBatch,
    ResourceDefinition,
    SeasonalSignal,
)

_EPSILON = 1e-9


class RealityEngine:
    """Own material, continuous and natural-field transitions.

    No material output exists without an explicit source, a registered process,
    or an extraction from physical natural stock. Natural fields remain outside
    inventory until extraction, preventing double-counting of resources still
    standing in a forest, aquifer or mineral deposit.
    """

    def __init__(self, state: RealityState | None = None) -> None:
        self.state = state or RealityState()

    # -- registration -------------------------------------------------------------
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
        if definition.code in self.state.processes or definition.code in self.state.continuous_processes:
            raise ValueError(f"process already exists: {definition.code}")
        unknown = (
            set(definition.inputs) | set(definition.outputs) | set(definition.byproducts)
        ) - set(self.state.resources)
        if unknown:
            raise ValueError(f"process {definition.code} uses unknown resources: {sorted(unknown)}")
        self.state.processes[definition.code] = definition

    def register_continuous_process(self, definition: ContinuousProcessDefinition) -> None:
        if definition.code in self.state.processes or definition.code in self.state.continuous_processes:
            raise ValueError(f"process already exists: {definition.code}")
        unknown = (
            set(definition.inputs_per_progress)
            | set(definition.outputs)
            | set(definition.byproducts)
        ) - set(self.state.resources)
        if unknown:
            raise ValueError(f"process {definition.code} uses unknown resources: {sorted(unknown)}")
        self.state.continuous_processes[definition.code] = definition

    def register_seasonal_signal(self, signal: SeasonalSignal) -> None:
        current = self.state.seasonal_signals.get(signal.metric)
        if current is not None and current != signal:
            raise ValueError(f"seasonal signal already registered differently: {signal.metric}")
        self.state.seasonal_signals[signal.metric] = signal

    def add_field(self, natural_field: NaturalField) -> NaturalField:
        if natural_field.field_id in self.state.fields:
            raise ValueError(f"field already exists: {natural_field.field_id}")
        self._location(natural_field.location_id)

        for rule in natural_field.rules:
            if rule.stock_metric not in natural_field.stocks:
                raise ValueError(
                    f"field rule {rule.code} targets unknown stock: {rule.stock_metric}"
                )
            coupled = set(rule.input_stocks_per_unit) | set(rule.output_stocks_per_unit)
            unknown = coupled - set(natural_field.stocks)
            if unknown:
                raise ValueError(
                    f"field rule {rule.code} couples unknown stocks: {sorted(unknown)}"
                )
            if rule.stock_metric in coupled:
                raise ValueError(
                    f"field rule {rule.code} cannot couple its target stock to itself"
                )

        for stock_metric, resource_code in natural_field.extractable_as.items():
            resource = self._resource(resource_code)
            stock_unit = natural_field.stock_units[stock_metric]
            if resource.unit != stock_unit:
                raise ValueError(
                    f"field stock {stock_metric} unit {stock_unit} does not match "
                    f"resource {resource_code} unit {resource.unit}"
                )

        natural_field.last_updated_minute = self.state.minute
        self.state.fields[natural_field.field_id] = natural_field
        return natural_field

    # -- world state --------------------------------------------------------------
    def set_environment(self, metric: str, value: float, *, location_id: str | None = None) -> None:
        if location_id is None:
            self.state.environment[metric] = float(value)
        else:
            self._location(location_id).environment[metric] = float(value)

    def set_state_variable(self, location_id: str, metric: str, value: float) -> None:
        self._location(location_id).state_variables[metric] = float(value)

    def seasonal_environment(self, minute: float | None = None) -> dict[str, float]:
        at = self.state.minute if minute is None else minute
        return {
            metric: signal.value_at(at)
            for metric, signal in self.state.seasonal_signals.items()
        }

    def environment_at(self, location_id: str) -> dict[str, float]:
        location = self._location(location_id)
        merged = self.seasonal_environment()
        merged.update(self.state.environment)
        merged.update(location.environment)
        merged.update(location.state_variables)
        return merged

    # -- explicit origins ---------------------------------------------------------
    def seed_resource(
        self,
        location_id: str,
        resource_code: str,
        quantity: float,
        *,
        source: str,
    ) -> ResourceBatch:
        """Create explicit Genesis/import stock with an auditable origin."""

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

    def extract_from_field(
        self,
        field_id: str,
        stock_metric: str,
        quantity: float,
        *,
        duration_minutes: int,
    ) -> ResourceBatch:
        """Move natural stock into material inventory after simulated extraction time.

        This is deliberately not ``seed_resource``. The quantity is deducted
        from an existing physical field stock and the resulting batch records
        the field as its provenance source. v0.4 can place labour/equipment and
        permits around this primitive without changing its accounting meaning.
        """

        if quantity <= 0:
            raise ValueError("field extraction quantity must be positive")
        if duration_minutes <= 0:
            raise ValueError("field extraction must take positive simulated time")
        field_state = self._field(field_id)
        try:
            resource_code = field_state.extractable_as[stock_metric]
        except KeyError as exc:
            raise ValueError(
                f"field stock is not extractable: {field_id}.{stock_metric}"
            ) from exc

        # Extraction itself consumes world time, so every other running system
        # continues to evolve while the operation is underway.
        self.advance(duration_minutes)

        available = field_state.quantity(stock_metric)
        if available + _EPSILON < quantity:
            raise ValueError(
                f"insufficient field stock {field_id}.{stock_metric}: "
                f"{available:.6f} < {quantity:.6f}"
            )
        field_state.stocks[stock_metric] = max(0.0, available - quantity)

        resource = self._resource(resource_code)
        location = self._location(field_state.location_id)
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
            kind="field_extraction",
            minute=self.state.minute,
            process_id="",
            resource_code=resource_code,
            quantity=float(quantity),
            output_batch_id=batch_id,
            source=f"field:{field_id}:{stock_metric}",
        )
        return batch

    # -- finite processes (v0.1) -------------------------------------------------
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
            if not condition.accepts(self.environment_at(source.location_id))
        ]
        if missing_conditions:
            raise ValueError(
                f"conditions not satisfied for {definition_code}: {sorted(missing_conditions)}"
            )

        # Validate all inputs first so start is atomic.
        for resource_code, quantity in definition.inputs.items():
            available = source.quantity(resource_code)
            if available + _EPSILON < quantity:
                raise ValueError(
                    f"insufficient {resource_code} at {source.location_id}: "
                    f"{available:.6f} < {quantity:.6f}"
                )

        consumed: list[ConsumedResource] = []
        for resource_code, quantity in definition.inputs.items():
            for batch, amount in source.consume(resource_code, quantity):
                consumed.append(self._consumed(resource_code, batch, amount))

        process_id = self._next_process_id()
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

    # -- continuous processes (v0.2) --------------------------------------------
    def start_continuous(
        self,
        definition_code: str,
        *,
        location_id: str,
        output_location_id: str | None = None,
    ) -> ContinuousProcessInstance:
        definition = self.state.continuous_processes[definition_code]
        location = self._location(location_id)
        self._location(output_location_id or location_id)

        current = location.state_variables.setdefault(
            definition.state_metric, float(definition.initial_value)
        )
        direction = 1.0 if definition.target_value > current else -1.0
        if direction * (definition.target_value - current) <= _EPSILON:
            raise ValueError(
                f"{definition.state_metric} already at or beyond target for {definition_code}"
            )

        process_id = self._next_process_id()
        instance = ContinuousProcessInstance(
            process_id=process_id,
            definition_code=definition.code,
            location_id=location_id,
            output_location_id=output_location_id or location_id,
            started_minute=self.state.minute,
            value=float(current),
        )
        self.state.continuous_running[process_id] = instance
        return instance

    # -- clock --------------------------------------------------------------------
    def advance(self, minutes: int) -> None:
        if minutes < 0:
            raise ValueError("minutes must be non-negative")
        target = self.state.minute + minutes

        while self.state.minute < target:
            self._update_due_fields()
            self._finish_ready()
            remaining_window = target - self.state.minute
            boundaries: list[int] = [remaining_window]

            for instance in self.state.running.values():
                if instance.status is not ProcessStatus.RUNNING:
                    continue
                definition = self.state.processes[instance.definition_code]
                remaining = definition.duration_minutes - instance.elapsed_minutes
                if remaining > 0:
                    boundaries.append(max(1, remaining))

            for instance in self.state.continuous_running.values():
                boundary = self._continuous_boundary_minutes(instance)
                if boundary is not None:
                    boundaries.append(boundary)

            for field_state in self.state.fields.values():
                if not field_state.active or not field_state.rules:
                    continue
                until_due = (
                    field_state.last_updated_minute
                    + field_state.resolution_minutes
                    - self.state.minute
                )
                boundaries.append(max(1, until_due))

            delta = max(1, min(boundaries))
            delta = min(delta, remaining_window)
            self._progress_fixed(delta)
            self._progress_continuous(delta)
            self.state.minute += delta
            self._update_due_fields()
            self._finish_ready()

    # -- provenance ---------------------------------------------------------------
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

    # -- natural-field internals (v0.3) ------------------------------------------
    def _update_due_fields(self) -> None:
        for field_id in sorted(self.state.fields):
            field_state = self.state.fields[field_id]
            if not field_state.active or not field_state.rules:
                continue
            while (
                field_state.last_updated_minute + field_state.resolution_minutes
                <= self.state.minute
            ):
                end_minute = field_state.last_updated_minute + field_state.resolution_minutes
                self._integrate_field(field_state, end_minute)
                field_state.last_updated_minute = end_minute

    def _integrate_field(self, field_state: NaturalField, end_minute: int) -> None:
        start_minute = field_state.last_updated_minute
        delta_minutes = end_minute - start_minute
        if delta_minutes <= 0:
            return
        delta_days = delta_minutes / 1440.0
        midpoint = start_minute + delta_minutes / 2.0

        location = self._location(field_state.location_id)
        environment = {
            metric: signal.value_at(midpoint)
            for metric, signal in self.state.seasonal_signals.items()
        }
        environment.update(self.state.environment)
        environment.update(location.environment)
        environment.update(location.state_variables)
        environment.update(field_state.environment)

        for rule in sorted(field_state.rules, key=lambda item: item.code):
            # Later rules in the same field interval can react to stocks changed
            # by earlier rules (rain recharge before growth, for example).
            environment.update(field_state.stocks)
            if not all(condition.accepts(environment) for condition in rule.conditions):
                continue

            factor = 1.0
            for modifier in rule.rate_modifiers:
                factor *= modifier.factor(environment)
            if factor <= _EPSILON:
                continue

            current = field_state.stocks[rule.stock_metric]
            change = rule.base_rate_per_day * delta_days * factor
            if change > 0 and rule.logistic and rule.maximum_value is not None:
                carrying = max(_EPSILON, rule.maximum_value)
                change *= max(0.0, 1.0 - current / carrying)

            if change > 0:
                if rule.maximum_value is not None:
                    change = min(change, max(0.0, rule.maximum_value - current))
            else:
                change = max(change, rule.minimum_value - current)

            magnitude = abs(change)
            if magnitude <= _EPSILON:
                continue

            for stock_metric, per_unit in rule.input_stocks_per_unit.items():
                if per_unit <= _EPSILON:
                    continue
                magnitude = min(
                    magnitude,
                    field_state.stocks[stock_metric] / per_unit,
                )
            if magnitude <= _EPSILON:
                continue

            signed_change = magnitude if change > 0 else -magnitude
            for stock_metric, per_unit in rule.input_stocks_per_unit.items():
                field_state.stocks[stock_metric] = max(
                    0.0,
                    field_state.stocks[stock_metric] - per_unit * magnitude,
                )

            field_state.stocks[rule.stock_metric] = min(
                rule.maximum_value if rule.maximum_value is not None else math.inf,
                max(rule.minimum_value, current + signed_change),
            )

            for stock_metric, per_unit in rule.output_stocks_per_unit.items():
                field_state.stocks[stock_metric] += per_unit * magnitude

    # -- finite internals ---------------------------------------------------------
    def _progress_fixed(self, delta: int) -> None:
        if delta <= 0:
            return
        for instance in self.state.running.values():
            if instance.status is not ProcessStatus.RUNNING:
                continue
            definition = self.state.processes[instance.definition_code]
            environment = self.environment_at(instance.input_location_id)
            if all(condition.accepts(environment) for condition in definition.conditions):
                instance.elapsed_minutes = min(
                    definition.duration_minutes,
                    instance.elapsed_minutes + delta,
                )
            else:
                instance.status = ProcessStatus.BLOCKED
                instance.note = "environment condition failed"

    def _finish_fixed(self, instance: ProcessInstance) -> None:
        if instance.status is not ProcessStatus.RUNNING:
            return
        definition = self.state.processes[instance.definition_code]
        if instance.elapsed_minutes < definition.duration_minutes:
            return
        self._emit_products(
            process_id=instance.process_id,
            output_location_id=instance.output_location_id,
            consumed=instance.consumed,
            outputs=definition.outputs,
            byproducts=definition.byproducts,
        )
        instance.status = ProcessStatus.COMPLETE
        instance.note = "complete"

    # -- continuous internals -----------------------------------------------------
    def _continuous_rate(self, instance: ContinuousProcessInstance) -> float:
        definition = self.state.continuous_processes[instance.definition_code]
        environment = self.environment_at(instance.location_id)
        if not all(condition.accepts(environment) for condition in definition.conditions):
            return 0.0
        factor = 1.0
        for modifier in definition.rate_modifiers:
            factor *= modifier.factor(environment)
        return definition.base_rate_per_minute * max(0.0, factor)

    def _continuous_boundary_minutes(self, instance: ContinuousProcessInstance) -> int | None:
        if instance.status is ProcessStatus.COMPLETE:
            return None
        definition = self.state.continuous_processes[instance.definition_code]
        rate = self._continuous_rate(instance)
        if rate <= _EPSILON:
            return None
        remaining_progress = abs(definition.target_value - instance.value)
        if remaining_progress <= _EPSILON:
            return 1

        location = self._location(instance.location_id)
        possible_progress = remaining_progress
        for resource_code, per_progress in definition.inputs_per_progress.items():
            if per_progress <= _EPSILON:
                continue
            possible_progress = min(
                possible_progress,
                location.quantity(resource_code) / per_progress,
            )
        if possible_progress <= _EPSILON:
            return None
        return max(1, int(math.ceil(possible_progress / rate)))

    def _progress_continuous(self, delta: int) -> None:
        if delta <= 0:
            return
        for instance in self.state.continuous_running.values():
            if instance.status is ProcessStatus.COMPLETE:
                continue
            definition = self.state.continuous_processes[instance.definition_code]
            environment = self.environment_at(instance.location_id)

            if not all(condition.accepts(environment) for condition in definition.conditions):
                instance.status = ProcessStatus.BLOCKED
                instance.note = "environment condition failed"
                continue

            rate = self._continuous_rate(instance)
            if rate <= _EPSILON:
                instance.status = ProcessStatus.BLOCKED
                instance.note = "environment rate is zero"
                continue

            remaining_progress = abs(definition.target_value - instance.value)
            desired_progress = min(remaining_progress, rate * delta)
            location = self._location(instance.location_id)
            possible_progress = desired_progress
            limiting_resource = ""
            for resource_code, per_progress in definition.inputs_per_progress.items():
                if per_progress <= _EPSILON:
                    continue
                resource_progress = location.quantity(resource_code) / per_progress
                if resource_progress + _EPSILON < possible_progress:
                    possible_progress = max(0.0, resource_progress)
                    limiting_resource = resource_code

            if possible_progress <= _EPSILON:
                instance.status = ProcessStatus.BLOCKED
                instance.note = f"insufficient {limiting_resource or 'continuous input'}"
                continue

            for resource_code, per_progress in definition.inputs_per_progress.items():
                quantity = per_progress * possible_progress
                if quantity <= _EPSILON:
                    continue
                for batch, amount in location.consume(resource_code, quantity):
                    instance.consumed.append(self._consumed(resource_code, batch, amount))

            direction = 1.0 if definition.target_value > instance.value else -1.0
            instance.value += direction * possible_progress
            if abs(instance.value - definition.target_value) <= _EPSILON:
                instance.value = float(definition.target_value)
            location.state_variables[definition.state_metric] = instance.value
            instance.elapsed_minutes += delta

            if possible_progress + _EPSILON < desired_progress:
                instance.status = ProcessStatus.BLOCKED
                instance.note = f"insufficient {limiting_resource or 'continuous input'}"
            else:
                instance.status = ProcessStatus.RUNNING
                instance.note = ""

    def _finish_continuous(self, instance: ContinuousProcessInstance) -> None:
        if instance.status is ProcessStatus.COMPLETE:
            return
        definition = self.state.continuous_processes[instance.definition_code]
        if abs(instance.value - definition.target_value) > _EPSILON:
            return
        self._emit_products(
            process_id=instance.process_id,
            output_location_id=instance.output_location_id,
            consumed=instance.consumed,
            outputs=definition.outputs,
            byproducts=definition.byproducts,
        )
        instance.status = ProcessStatus.COMPLETE
        instance.note = "complete"

    def _finish_ready(self) -> None:
        for instance in self.state.running.values():
            self._finish_fixed(instance)
        for instance in self.state.continuous_running.values():
            self._finish_continuous(instance)

    # -- shared internals ---------------------------------------------------------
    def _emit_products(
        self,
        *,
        process_id: str,
        output_location_id: str,
        consumed: tuple[ConsumedResource, ...] | list[ConsumedResource],
        outputs: dict[str, float],
        byproducts: dict[str, float],
    ) -> None:
        destination = self._location(output_location_id)
        parent_batch_ids = tuple(sorted({entry.batch_id for entry in consumed}))
        for resource_code, quantity in list(outputs.items()) + list(byproducts.items()):
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
                process_id=process_id,
                resource_code=resource_code,
                quantity=float(quantity),
                output_batch_id=batch_id,
                input_batch_ids=parent_batch_ids,
            )

    @staticmethod
    def _consumed(resource_code: str, batch: ResourceBatch, amount: float) -> ConsumedResource:
        return ConsumedResource(
            resource_code=resource_code,
            quantity=amount,
            batch_id=batch.batch_id,
            provenance_event_id=batch.provenance_event_id,
        )

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

    def _field(self, field_id: str) -> NaturalField:
        try:
            return self.state.fields[field_id]
        except KeyError as exc:
            raise KeyError(f"unknown natural field: {field_id}") from exc

    def _next_batch_id(self) -> str:
        self.state.next_batch_index += 1
        return f"batch_{self.state.next_batch_index:08d}"

    def _next_process_id(self) -> str:
        self.state.next_process_index += 1
        return f"proc_{self.state.next_process_index:08d}"

    def _next_event_id(self) -> str:
        self.state.next_event_index += 1
        return f"reality_{self.state.next_event_index:08d}"
