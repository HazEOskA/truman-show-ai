# Hydra Reality Engine v0.2 — Continuous Reality

## Purpose

v0.1 proved that material transformations can be deterministic, located, timed and auditable.
v0.2 extends the same reality model to processes that evolve continuously instead of finishing after a fixed recipe timer.

Examples:

- tree biomass growth;
- crop growth;
- heating and cooling;
- cooking progress;
- battery charge;
- concrete curing;
- machine wear;
- healing;
- drying and fermentation.

## Core rule

A continuous process is:

`state + environment + resources + simulated time -> next state`

The engine owns progression. Domain data owns the parameters.

No species, recipe or object type receives bespoke engine code.

## ContinuousProcessDefinition

A definition contains:

- `state_metric` — scalar state being changed, e.g. `biomass_kg`, `water_temperature_c`, `cook_fraction`;
- `initial_value`;
- `target_value`;
- `base_rate_per_minute`;
- `conditions` — hard gates which must be satisfied;
- `rate_modifiers` — environmental response curves;
- `inputs_per_progress` — resources consumed per unit of actual state change;
- optional material outputs and byproducts emitted at completion.

The target may be higher or lower than the initial value, so the same contract covers heating and cooling.

## Rate modifiers

v0.2 uses a deterministic piecewise-linear response curve:

`minimum -> optimum_min -> optimum_max -> maximum`

Rate is zero outside the viable range, rises to 100% across the lower shoulder, stays at 100% in the optimum band and falls back to zero across the upper shoulder.

Multiple modifiers multiply together.

Example tree rate:

`base_growth × temperature_factor × sunlight_factor`

A hard soil-moisture condition can stop the process entirely.

## Resource coupling

Continuous resources are charged per unit of actual progress, not per wall-clock minute.

If a tree grows only 0.2 kg of biomass because sunlight is poor, water/nutrients are consumed only for that 0.2 kg.

If required material becomes unavailable, the process becomes `BLOCKED` and stops changing reality.

## Environment scopes

Environment is resolved in this order:

1. global world environment;
2. location environment;
3. location state variables.

Later scopes override earlier ones.

This allows a process condition to read a state created by another process. Example:

`heat_water` changes `water_temperature_c`;

then

`boil_potatoes` requires `water_temperature_c >= 95`.

## Time

The scheduler remains event-boundary based.

It advances to the earliest relevant boundary among:

- requested target time;
- finite-process completion;
- continuous-process completion or resource exhaustion under the current environment.

The engine therefore does not require a one-minute poll for a process lasting decades when its rate and environment are unchanged.

## Acceptance scenario A — tree growth

A forest location contains explicit water stock and environmental values for sunlight, soil moisture and temperature.

A generic continuous definition grows `tree_biomass_kg` toward a target and emits `standing_timber` only after the target is reached.

Assertions:

- optimal conditions produce expected growth;
- water is consumed proportional to biomass gained;
- drought blocks progress;
- restoring conditions resumes the same process;
- final timber has provenance back to the explicit water/material inputs used by growth.

## Acceptance scenario B — potato cooking

1. `heat_water` raises `water_temperature_c` from 20°C to 100°C while consuming electricity per degree.
2. `boil_potato` advances `cook_fraction` from 0 to 1 only while `water_temperature_c >= 95°C`.
3. The process consumes the raw potato and produces a cooked potato after 30 simulated minutes at boiling conditions.
4. `cool_water` demonstrates the same continuous contract in the opposite direction, reducing temperature toward ambient.

## Invariants retained from v0.1

1. NOTHING FROM NOTHING.
2. EVERYTHING EXISTS SOMEWHERE.
3. EVERY TRANSFORMATION TAKES TIME.
4. EVERY PROCESS HAS CONDITIONS / COSTS.
5. EVERY MATERIAL OUTPUT HAS PROVENANCE.
6. SIMULATE ONLY AS DEEPLY AS NECESSARY.

## Still out of scope

- differential-equation solvers;
- phase-change thermodynamics;
- chemistry/reaction balancing;
- spatial diffusion of temperature/moisture;
- procedural weather generation;
- species database and agricultural knowledge packs;
- automatic process-graph planning by agents;
- integration into the production Hydra kernel.

Those remain data/domain layers or later engine increments rather than reasons to special-case v0.2.
