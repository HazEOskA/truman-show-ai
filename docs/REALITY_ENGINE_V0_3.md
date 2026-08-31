# Hydra Reality Engine v0.3 — Fields & Natural Cycles

## Purpose

v0.1 made material transformations auditable. v0.2 made state transitions continuous.
v0.3 gives those processes a physical planet substrate: forests, farmland, aquifers,
wetlands and mineral deposits that exist in a place, change with time and can be depleted.

The central distinction is:

- **field stock** = matter still physically in the environment;
- **inventory batch** = matter that has been extracted/harvested and can enter logistics,
  manufacturing and markets.

A forest containing 10,000 kg of harvestable biomass must not also expose 10,000 kg of
inventory timber. Material crosses that boundary only through an explicit extraction event.

## New primitives

### NaturalField

A spatially anchored area with:

- `field_id`;
- `FieldKind` (`forest`, `farmland`, `aquifer`, `deposit`, `wetland`, `grassland`);
- physical `location_id`;
- area in hectares;
- scalar physical stocks;
- units for every stock;
- optional stock -> inventory-resource extraction mapping;
- deterministic field rules;
- local environmental overrides;
- simulation resolution / LOD interval.

Examples of field stocks:

```text
forest:
  biomass_kg
  soil_water_l
  soil_nutrients_kg

farmland:
  crop_biomass_kg
  soil_water_l
  nitrogen_kg

 aquifer:
  groundwater_m3

 deposit:
  iron_ore_kg
  copper_ore_kg
```

## FieldRule

A field rule is a reusable rate equation:

```text
stock_change = base_rate × elapsed_days × environment_factor
```

It may also:

- require environmental conditions;
- use `RateModifier` curves for temperature, water, light, rainfall etc.;
- consume other field stocks per unit of change;
- produce coupled stocks;
- clamp a stock to physical min/max;
- use logistic carrying-capacity growth.

This allows one engine primitive to represent:

- forest biomass growth;
- crop growth;
- rainfall recharge;
- evapotranspiration;
- groundwater recharge;
- wetland recovery;
- soil nutrient regeneration/depletion;
- natural decay.

Mineral deposits simply have no positive renewal rule.

## Logistic renewable growth

Renewable stocks can slow near carrying capacity:

```text
effective_growth = base_growth × environment_factor × (1 - stock / capacity)
```

This prevents a forest from increasing forever while retaining deterministic and cheap
regional simulation.

## SeasonalSignal

Seasonality is deterministic periodic forcing:

```text
value(t) = mean + amplitude × sin(2π × phase(t))
```

A signal can drive:

- daylight;
- temperature tendency;
- rainfall tendency;
- river flow;
- seasonal productivity.

Explicit world/location weather values override the seasonal baseline, so future seeded
storms, droughts, heatwaves and climate systems can reuse the same metrics.

## Field simulation LOD

A natural field has `resolution_minutes`.

Examples:

```text
street greenhouse       60 min
crop field              360 min
forest                  1440 min
remote wilderness       10080 min
mineral deposit         no autonomous update
```

The global clock schedules the next field boundary rather than polling every field every
minute. This keeps the same reality model while changing only simulation depth.

## Extraction boundary

`extract_from_field()` is the only v0.3 path from natural stock to inventory.

Rules:

1. the field stock must exist;
2. the stock must explicitly map to an inventory resource;
3. field-stock and resource units must match;
4. extraction takes positive simulated time;
5. the quantity is deducted from the field;
6. an inventory `ResourceBatch` is created at the field location;
7. provenance records `field:<field_id>:<stock_metric>`.

Example:

```text
forest.biomass_kg = 12,000

extract 2,000 kg over 6 simulated hours

forest.biomass_kg = 10,000
forest_location.inventory.standing_timber += 2,000 kg
provenance.source = field:forest_001:biomass_kg
```

No duplicate material is created.

## Acceptance scenario A — living forest

A forest starts with biomass, soil water and nutrients.

- with sufficient water/light/temperature, biomass grows;
- growth consumes water and nutrients;
- without rain, soil water reaches drought level;
- biomass growth pauses;
- rainfall replenishes soil water;
- growth resumes;
- harvesting removes biomass from the field and creates traceable timber inventory.

## Acceptance scenario B — finite deposit

An ore deposit starts with a finite underground reserve.

- extraction reduces the reserve;
- extracted ore appears as inventory at the mine;
- advancing years does not regenerate the deposit unless a rule explicitly says so.

## Acceptance scenario C — deterministic season

Given the same world minute and signal definition, the seasonal environment is identical.
A four-day test cycle reaches known extrema at known simulation days, proving the clock is
the source of season state rather than wall time.

## Still out of scope

v0.3 deliberately does not yet implement:

- terrain grid / parcel topology;
- river flow networks;
- seeded stochastic weather events;
- fire spread;
- pests/disease ecology;
- explicit species populations;
- extraction equipment, labour and permits;
- vehicle routing;
- automatic land-use decisions;
- agent planning over natural capital;
- rendering vegetation/terrain in Observatory.

These become data and systems built on the field contract rather than reasons to replace it.
