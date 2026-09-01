# Hydra Reality Engine v0.1 — Architecture Lock

## Purpose

Hydra must not create material outcomes from narrative shortcuts. The Reality Engine is the deterministic physical/process substrate beneath geography, companies, markets and agents.

It answers four questions for every material change:

1. What existed before?
2. Where did it exist?
3. What process transformed or moved it?
4. How much simulated time did that process consume?

## Hard invariants

1. **NOTHING FROM NOTHING** — material output must come from explicit origin stock or a registered transformation.
2. **EVERYTHING EXISTS SOMEWHERE** — every material batch belongs to a location.
3. **EVERY TRANSFORMATION TAKES TIME** — processes have positive simulated duration.
4. **EVERY PROCESS HAS INPUTS / CONDITIONS / COSTS** — no narrative completion path may bypass them.
5. **EVERY OUTPUT HAS PROVENANCE** — output batches reference the batches that caused them.
6. **SIMULATE ONLY AS DEEPLY AS NECESSARY** — detail is a simulation-LOD decision, not a different reality model.

## v0.1 primitives

### ResourceDefinition
Defines a resource code, physical/logical unit and category. Examples: `standing_timber:kg`, `electricity:kWh`, `labour:hour`, `chair:unit`.

### ResourceBatch
A quantity of one resource with a location, creation time and provenance event. Batches make causal ancestry auditable.

### Location
Owns inventory. Materials never teleport: a transport process consumes at one location and produces at another.

### Condition
A numeric environmental requirement such as minimum soil moisture, temperature band or sunlight.

### ProcessDefinition
A reusable recipe:

`inputs + conditions + simulated time -> outputs + byproducts`

The same contract represents harvesting, hauling, milling, manufacturing, cooking, charging, growth phases and construction steps.

### ProcessInstance
A running execution of one definition with explicit source/destination locations and elapsed simulated time.

### ProvenanceEvent
Records explicit origins and process outputs. A final object can be traced backwards through its material parents.

### RealityState
Contains simulation minute, registries, locations, running processes, environment and provenance ledger.

## Explicit origins

The engine needs one controlled escape hatch for Genesis/natural capital: `seed_resource(..., source=...)`.

This is not a hidden spawn. The source is mandatory and written to provenance, e.g.:

- `genesis:forest_cell_001`
- `genesis:ore_deposit_004`
- `genesis:groundwater_aquifer_02`

Later versions should replace broad Genesis stock with renewable/depletable field models (forest biomass, crops, deposits, reservoirs) that themselves emit extractable batches.

## Time model

v0.1 is event-boundary based. Processes do not need per-minute polling. The engine advances directly to the next meaningful completion boundary, preserving deterministic simulated time.

Future continuous processes (tree growth, crop growth, cooling, healing) keep the same contract but add rate integration and scheduled condition boundaries.

## First vertical slice: forest -> chair

Acceptance chain:

`standing timber -> harvest -> logs -> haul -> sawmill -> lumber + sawdust -> haul -> furniture factory -> chair -> delivery -> shop`

The test must prove:

- timber is consumed from an explicit forest origin;
- stock changes location only through a process;
- each stage consumes simulated time;
- no process starts without its material inputs;
- the final chair has a provenance chain back to the forest origin;
- byproducts exist rather than disappearing from accounting.

## Deliberately out of scope for v0.1

- full thermodynamics;
- chemistry/reaction balancing;
- continuous biological growth curves;
- vehicle routing/pathfinding;
- ownership/legal permissions;
- equipment wear and maintenance;
- automatic agent planning over the process graph;
- kernel integration and production deployment.

Those are v0.2+ layers. v0.1 locks the contracts they will build on.
