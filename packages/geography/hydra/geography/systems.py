"""Environment systems: weather, the power grid, water and transport.

The grid is deliberately the most detailed: it is the layer the rest of the city hangs off.
Losing generation here shows up as a price, then a cost, then a job — without anyone writing
a storyline.
"""

from __future__ import annotations

import math

from hydra.economy.model import EconomyState
from hydra.events.importance import ImportanceInputs
from hydra.events.model import Topics
from hydra.kernel.clock import TICKS_PER_DAY, TICKS_PER_HOUR
from hydra.kernel.systems import Phase, SystemSpec

from .model import GeographyState

# Relative electricity demand through the day, one entry per hour.
LOAD_PROFILE = (
    0.62, 0.58, 0.55, 0.54, 0.57, 0.66, 0.82, 0.96, 1.05, 1.08, 1.10, 1.12,
    1.14, 1.12, 1.09, 1.07, 1.10, 1.22, 1.30, 1.24, 1.10, 0.95, 0.82, 0.71,
)
MERIT_ORDER = {"solar": 0, "wind": 1, "hydro": 2, "fission": 3, "gas": 4}
PUBLIC_LOAD_KWH_PER_RESIDENT = 0.12     # per hour: lighting, pumps, transit, public buildings
GAS_FUEL_PER_KWH = 0.09                 # litres of fuel burned per kWh in a gas plant
DISPATCH_HEADROOM = 1.35                # generate ahead of the load the market last showed
BOOTSTRAP_LOAD_SHARE = 0.55             # first tick of a new world, before any load is known
RESERVE_COMFORT = 1.45                  # reserve margin below which power starts to cost more
SCARCITY_SLOPE = 2.2                    # how sharply a thin margin is priced


class WeatherSystem:
    spec = SystemSpec(
        name="weather",
        phase=Phase.ENVIRONMENT,
        cadence_ticks=TICKS_PER_HOUR,
        priority=5,
        reads=("geography",),
        writes=("geography",),
        emits=(Topics.ENV_WEATHER,),
        description="Seasonal temperature, precipitation and wind; drives heating and cooling load.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        geography = ctx.state.domain(GeographyState)
        region = next(iter(geography.regions.values()))
        rng = ctx.rng("weather")
        now = ctx.now

        season_phase = 2.0 * math.pi * (now.day_of_year / 360.0)
        daily_phase = 2.0 * math.pi * ((now.minutes_of_day / 1440.0) - 0.25)
        seasonal = 11.0 * math.sin(season_phase - math.pi / 2.0)
        diurnal = 4.5 * math.sin(daily_phase)
        weather = geography.weather
        weather.temperature_c = round(
            0.85 * weather.temperature_c + 0.15 * (region.temperature_c + seasonal + diurnal) + rng.normal(0.0, 0.35),
            3,
        )
        weather.precipitation_mm = round(max(0.0, rng.normal(0.6 if weather.cloud > 0.6 else 0.1, 0.9)), 3)
        weather.cloud = round(min(1.0, max(0.0, 0.9 * weather.cloud + 0.1 * rng.random())), 4)
        weather.wind_kph = round(max(0.0, 0.9 * weather.wind_kph + 0.1 * rng.uniform(0.0, 40.0)), 3)
        weather.season = ("winter", "spring", "summer", "autumn")[(now.month - 1) // 3]
        weather.heat_stress = round(max(0.0, (weather.temperature_c - 26.0) / 14.0), 4)
        weather.cold_stress = round(max(0.0, (2.0 - weather.temperature_c) / 16.0), 4)

        if weather.heat_stress > 0.5 or weather.cold_stress > 0.5:
            ctx.emit(
                Topics.ENV_WEATHER,
                "extreme_weather",
                location=geography.seed_city_id,
                payload={
                    "temperature_c": weather.temperature_c,
                    "heat_stress": weather.heat_stress,
                    "cold_stress": weather.cold_stress,
                },
                inputs=ImportanceInputs(
                    people_affected=region.population * 0.4,
                    risk=max(weather.heat_stress, weather.cold_stress) * 0.5,
                    political_impact=0.1,
                ),
            )


class PowerGridSystem:
    """Dispatches plants against demand and publishes the electricity supply to the market."""

    spec = SystemSpec(
        name="power_grid",
        phase=Phase.ENVIRONMENT,
        cadence_ticks=1,
        priority=10,
        reads=("geography", "agents", "economy"),
        writes=("geography", "economy"),
        emits=(Topics.ENV_POWER_OUTPUT, Topics.ENV_POWER_SHORTAGE),
        description="Merit-order dispatch, reliability per district, electricity supply to market.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        geography = ctx.state.domain(GeographyState)
        economy = ctx.state.domain(EconomyState)
        city = geography.city()
        infra = city.infrastructure
        weather = geography.weather
        now = ctx.now

        residents = sum(d.population for d in geography.districts.values())
        hour_factor = LOAD_PROFILE[now.hour]
        climate_factor = 1.0 + weather.heat_stress * 0.35 + weather.cold_stress * 0.45
        weekend_factor = 0.93 if now.is_weekend else 1.0

        # A grid follows load; it cannot wait to be told. Dispatching only what the market
        # bought last hour looks prudent and is a trap: constrained supply throttles
        # production, which lowers measured demand, which lowers supply again. So the target
        # is the recent load with headroom in front of it, and whatever is not sold expires.
        market = economy.markets["electricity"]
        measured_kwh = max(market.demand_ema, market.last_demand)
        if measured_kwh <= 0.0:
            measured_kwh = infra.power_capacity_mw * 1000.0 * BOOTSTRAP_LOAD_SHARE
        public_kwh = residents * PUBLIC_LOAD_KWH_PER_RESIDENT
        target_kwh = measured_kwh * DISPATCH_HEADROOM + public_kwh
        demand_mw = round(target_kwh / 1000.0 * climate_factor * weekend_factor * (0.85 + 0.15 * hour_factor), 4)
        infra.power_demand_mw = demand_mw
        # What the city actually needs, as opposed to what the grid aims to have ready.
        served_mw = max(1e-6, (measured_kwh + public_kwh) / 1000.0)

        plants = sorted(
            geography.power_plants.values(),
            key=lambda p: (MERIT_ORDER.get(p.fuel, 9), p.plant_id),
        )
        from hydra.companies.model import CompaniesState
        from hydra.economy.clearing import purchase

        companies = ctx.state.domain(CompaniesState)
        remaining = demand_mw
        dispatched = 0.0
        marginal_cost_per_mwh = 0
        for plant in plants:
            available = plant.capacity_mw * plant.availability
            if plant.fuel == "solar":
                daylight = max(0.0, math.sin(math.pi * (now.minutes_of_day / 1440.0)))
                available *= daylight * (1.0 - 0.6 * weather.cloud)
            take = max(0.0, min(available, remaining))
            plant.output_mw = round(take, 4)
            dispatched += take
            remaining -= take
            if take <= 0.0:
                continue
            # A generator's marginal cost is its own running cost plus the fuel it must buy
            # at today's price — which is why a gas plant gets dearer when fuel gets dearer.
            running_cost = float(plant.fuel_cost_per_mwh_minor)
            if plant.fuel == "gas":
                running_cost += economy.markets["fuel"].price_minor * GAS_FUEL_PER_KWH * 1000.0
            marginal_cost_per_mwh = max(marginal_cost_per_mwh, running_cost)

            # The operator sells this power and burns the fuel it took to make it.
            operator = companies.companies.get(plant.operator_id)
            if operator is None:
                continue
            kwh = take * 1000.0 / TICKS_PER_HOUR
            operator.output_units = round(kwh, 3)
            operator.supplied_window += kwh
            if plant.fuel == "gas":
                fuel_qty = kwh * GAS_FUEL_PER_KWH
                economy.markets["fuel"].demand += fuel_qty
                bought = purchase(
                    economy,
                    buyer_account_id=operator.account_id,
                    code="fuel",
                    quantity=fuel_qty,
                )
                operator.costs_minor += bought.spent_minor

        infra.power_output_mw = round(dispatched, 4)

        # Everyone pays what the last generator dispatched costs — the merit order is why an
        # outage at the cheap plant becomes an energy price shock rather than a footnote. On
        # top of that, a thin reserve margin is itself expensive: when the city is one fault
        # away from the lights going out, power is dear even before anything else changes.
        capacity_available = sum(p.capacity_mw * p.availability for p in plants)
        reserve_ratio = capacity_available / served_mw
        scarcity = 1.0 + max(0.0, RESERVE_COMFORT - reserve_ratio) * SCARCITY_SLOPE
        market.cost_override_minor = max(1, int(marginal_cost_per_mwh / 1000.0 * scarcity))
        ctx.telemetry.gauge("power_reserve_ratio", round(reserve_ratio, 4))
        ctx.telemetry.gauge("power_scarcity", round(scarcity, 4))

        reliability = min(1.0, dispatched / served_mw)
        for district in geography.districts.values():
            # Industry and the wealthy districts are shed last; the periphery feels it first.
            resilience = 0.35 + 0.65 * district.wealth_index
            district.power_reliability = round(min(1.0, reliability + (1.0 - reliability) * resilience * 0.5), 4)

        # Power reaches the market once per market cycle, as a whole hour of generation: a
        # factory buys an hour of electricity in one go, and it has to be there when it does.
        # The public load is consumed by the city itself and never reaches the market.
        if ctx.tick % TICKS_PER_HOUR == 0:
            sellable = max(0.0, dispatched * 1000.0 - residents * PUBLIC_LOAD_KWH_PER_RESIDENT)
            market.supply += sellable
            # Replaces, never accumulates: an hour's power is available for that hour only.
            market.inventory = sellable

        if reliability < 0.995:
            deficit = round(demand_mw - dispatched, 3)
            if ctx.tick % 6 == 0 or reliability < 0.9:
                ctx.emit(
                    Topics.ENV_POWER_SHORTAGE,
                    "power_shortage",
                    location=geography.seed_city_id,
                    payload={
                        "demand_mw": demand_mw,
                        "supply_mw": round(dispatched, 3),
                        "deficit_mw": deficit,
                        "reliability": round(reliability, 4),
                    },
                    inputs=ImportanceInputs(
                        people_affected=residents * (1.0 - reliability),
                        economic_impact=deficit * 1000.0 * market.price_minor,
                        political_impact=0.55,
                        risk=0.5,
                    ),
                )
        ctx.telemetry.gauge("power_demand_mw", demand_mw)
        ctx.telemetry.gauge("power_output_mw", round(dispatched, 4))
        ctx.telemetry.gauge("power_reliability", round(reliability, 4))


class WaterSystem:
    spec = SystemSpec(
        name="water",
        phase=Phase.ENVIRONMENT,
        cadence_ticks=TICKS_PER_HOUR,
        priority=20,
        reads=("geography", "economy"),
        writes=("geography", "economy"),
        emits=(Topics.ENV_WATER,),
        description="Water production, constrained by power reliability, published to the market.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        geography = ctx.state.domain(GeographyState)
        economy = ctx.state.domain(EconomyState)
        city = geography.city()
        infra = city.infrastructure
        reliability = min(
            1.0, infra.power_output_mw / max(1e-6, infra.power_demand_mw)
        )
        region = next(iter(geography.regions.values()))
        output = infra.water_capacity_m3 * min(1.0, region.water + 0.1) * reliability / 24.0
        infra.water_output_m3 = round(output * 24.0, 3)
        economy.markets["water"].supply += output
        economy.markets["water"].inventory = output
        if reliability < 0.9:
            ctx.emit(
                Topics.ENV_WATER,
                "water_pressure_drop",
                location=geography.seed_city_id,
                payload={"reliability": round(reliability, 4), "output_m3_day": infra.water_output_m3},
                inputs=ImportanceInputs(
                    people_affected=region.population * 0.3,
                    risk=0.35,
                    political_impact=0.3,
                ),
            )


class TransportSystem:
    spec = SystemSpec(
        name="transport",
        phase=Phase.ENVIRONMENT,
        cadence_ticks=1,
        priority=30,
        reads=("geography", "agents", "economy"),
        writes=("geography", "economy"),
        emits=(Topics.TRANSPORT_CONGESTION,),
        description="Commuting load per district; congestion feeds logistics cost and mood.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        geography = ctx.state.domain(GeographyState)
        economy = ctx.state.domain(EconomyState)
        now = ctx.now
        peak = 1.0 if now.hour in (7, 8, 16, 17, 18) else 0.45 if 9 <= now.hour <= 15 else 0.15
        if now.is_weekend:
            peak *= 0.6

        total_load = 0.0
        worst = None
        for district in geography.districts.values():
            capacity = max(0.1, district.transport_capacity)
            load = district.population * 0.00035 * peak * (1.0 + district.pollution)
            district.transport_load = round(load, 4)
            ratio = load / capacity
            total_load += ratio
            if worst is None or ratio > worst[1]:
                worst = (district.district_id, ratio)

        city = geography.city()
        city.infrastructure.road_load = round(total_load, 4)
        # Congestion does not create transport; it makes moving anything more expensive.
        congestion = total_load / max(1, len(geography.districts))
        market = economy.markets["transport"]
        market.unit_cost_minor = int(market.unit_cost_minor * (1.0 + max(0.0, congestion - 1.0) * 0.02))

        if worst and worst[1] > 1.35:
            ctx.emit(
                Topics.TRANSPORT_CONGESTION,
                "congestion",
                location=worst[0],
                payload={"load_ratio": round(worst[1], 3)},
                importance=0.08,
            )
