"""Genesis of the physical world.

Hydra is a designed seed city — districts, plants and civic buildings are laid out
deliberately — but every quantity inside that layout is drawn from the district's derived
seed, so two worlds with different master seeds get genuinely different cities.
"""

from __future__ import annotations

from dataclasses import dataclass

from hydra.geography.model import (
    Building,
    BuildingKind,
    City,
    Climate,
    Continent,
    Coordinates,
    Country,
    District,
    DistrictKind,
    GeographyState,
    Infrastructure,
    Planet,
    PowerPlant,
    Region,
    Weather,
)
from hydra.kernel.ids import building_id as make_building_id
from hydra.kernel.rng import DeterministicRng

from .names import place_name, word
from .seeds import SeedTree


@dataclass(frozen=True, slots=True)
class DistrictBlueprint:
    key: str
    name: str
    kind: DistrictKind
    population_share: float
    wealth: float
    area_km2: float
    pollution: float
    crime: float
    x: float
    y: float


HYDRA_DISTRICTS: tuple[DistrictBlueprint, ...] = (
    DistrictBlueprint("hydra_core", "Hydra Core", DistrictKind.COMMERCIAL, 0.08, 0.72, 4.2, 0.14, 0.028, 0.0, 0.0),
    DistrictBlueprint("kestrel_heights", "Kestrel Heights", DistrictKind.ELITE, 0.07, 0.90, 6.5, 0.06, 0.008, 3.1, 2.6),
    DistrictBlueprint("lantern_quarter", "Lantern Quarter", DistrictKind.MIXED, 0.14, 0.55, 5.1, 0.12, 0.031, -2.4, 1.8),
    DistrictBlueprint("hydra_west", "Hydra West", DistrictKind.RESIDENTIAL, 0.22, 0.45, 9.4, 0.16, 0.037, -5.2, -0.6),
    DistrictBlueprint("steelgate", "Steelgate", DistrictKind.INDUSTRIAL, 0.11, 0.35, 11.8, 0.42, 0.052, 4.6, -3.4),
    DistrictBlueprint("old_port", "Old Port", DistrictKind.PORT, 0.10, 0.40, 7.7, 0.31, 0.061, 1.2, -5.8),
    DistrictBlueprint("marrow_row", "Marrow Row", DistrictKind.PERIPHERY, 0.16, 0.20, 8.9, 0.27, 0.094, -6.8, -4.9),
    DistrictBlueprint("verge", "The Verge", DistrictKind.RESIDENTIAL, 0.12, 0.50, 12.6, 0.09, 0.024, 6.9, 3.9),
)

# (kind, count, capacity each, fixed district key or None to spread across the city)
CIVIC_PLAN: tuple[tuple[BuildingKind, int, int, str | None], ...] = (
    (BuildingKind.CITY_HALL, 1, 400, "hydra_core"),
    (BuildingKind.COURT, 1, 180, "hydra_core"),
    (BuildingKind.POLICE, 3, 120, None),
    (BuildingKind.HOSPITAL, 2, 600, None),
    (BuildingKind.SCHOOL, 7, 700, None),
    (BuildingKind.UNIVERSITY, 1, 5200, "lantern_quarter"),
    (BuildingKind.TRANSPORT_HUB, 2, 9000, None),
    (BuildingKind.DATA_CENTRE, 2, 60, None),
    (BuildingKind.CULTURE, 3, 500, None),
    (BuildingKind.WATER_PLANT, 1, 0, "old_port"),
)

# plant id, fuel, share of installed capacity, district, fuel cost per MWh (minor)
# plant id, fuel, share of installed capacity, district, running cost per MWh excluding fuel
# (minor units). Fuel-burning plants add the market price of the fuel they actually consume.
PLANT_PLAN: tuple[tuple[str, str, float, str, int], ...] = (
    ("plant_kelvar", "fission", 0.780, "district_steelgate", 2_800),
    ("plant_portgas", "gas", 0.160, "district_old_port", 1_500),
    ("plant_verge_solar", "solar", 0.060, "district_verge", 300),
)
DEFAULT_INSTALLED_MW = 80.0


def build_geography(
    seeds: SeedTree,
    total_residents: int,
    epoch_year: int,
    installed_power_mw: float = DEFAULT_INSTALLED_MW,
) -> GeographyState:
    state = GeographyState()
    prng = seeds.planet()

    state.planet = Planet(
        planet_id="planet_hydra",
        name=word(prng, 2),
        radius_km=round(prng.uniform(5800.0, 6700.0), 1),
        axial_tilt_deg=round(prng.uniform(18.0, 27.0), 2),
        year_days=360,
    )

    continent = Continent(
        continent_id="cont_meridia",
        name=place_name(seeds.continent("cont_meridia")),
        area_km2=round(prng.uniform(9.0e6, 1.8e7), 0),
    )
    state.continents[continent.continent_id] = continent
    state.planet.continent_ids.append(continent.continent_id)

    country_rng = seeds.country("country_valdris")
    country = Country(
        country_id="country_valdris",
        name=place_name(country_rng),
        continent_id=continent.continent_id,
        currency_code="HYD",
    )
    state.countries[country.country_id] = country
    continent.country_ids.append(country.country_id)

    region_rng = seeds.region("region_hydra_basin")
    region = Region(
        region_id="region_hydra_basin",
        country_id=country.country_id,
        name=f"{place_name(region_rng)} Basin",
        population=total_residents,
        area_km2=round(region_rng.uniform(2400.0, 4200.0), 1),
        climate=Climate.TEMPERATE,
        temperature_c=round(region_rng.uniform(9.0, 13.5), 2),
        water=round(region_rng.uniform(0.72, 0.95), 3),
        food=round(region_rng.uniform(0.6, 0.85), 3),
        energy=round(region_rng.uniform(0.65, 0.9), 3),
        resources={
            "silicon": round(region_rng.uniform(0.2, 0.7), 3),
            "copper": round(region_rng.uniform(0.15, 0.6), 3),
            "lithium": round(region_rng.uniform(0.05, 0.4), 3),
            "iron": round(region_rng.uniform(0.3, 0.8), 3),
            "gas": round(region_rng.uniform(0.1, 0.55), 3),
        },
        infrastructure=round(region_rng.uniform(0.55, 0.78), 3),
        industry=round(region_rng.uniform(0.45, 0.7), 3),
        wealth=round(region_rng.uniform(0.42, 0.62), 3),
        technology=round(region_rng.uniform(0.45, 0.65), 3),
        pollution=round(region_rng.uniform(0.1, 0.25), 3),
        political_stability=round(region_rng.uniform(0.6, 0.82), 3),
        transport_capacity=round(region_rng.uniform(0.55, 0.8), 3),
    )
    state.regions[region.region_id] = region
    country.region_ids.append(region.region_id)

    city_rng = seeds.city("city_hydra")
    city = City(
        city_id="city_hydra",
        name="Hydra",
        region_id=region.region_id,
        founded_year=epoch_year - city_rng.randint(180, 420),
        is_capital=True,
    )
    state.cities[city.city_id] = city
    state.seed_city_id = city.city_id
    region.city_ids.append(city.city_id)
    country.capital_city_id = city.city_id

    counter = _BuildingCounter()
    for blueprint in HYDRA_DISTRICTS:
        _build_district(state, seeds, blueprint, total_residents, counter, city)

    _build_civic(state, seeds, counter)
    _build_power(state, seeds, counter, installed_power_mw)

    city.infrastructure = Infrastructure(
        power_capacity_mw=sum(p.capacity_mw for p in state.power_plants.values()),
        power_output_mw=sum(p.output_mw for p in state.power_plants.values()),
        power_demand_mw=round(sum(p.capacity_mw for p in state.power_plants.values()) * 0.62, 3),
        water_capacity_m3=round(total_residents * 0.35, 1),
        water_output_m3=round(total_residents * 0.30, 1),
        road_capacity=round(total_residents * 0.22, 1),
        net_capacity_gbps=round(total_residents * 0.02, 2),
        condition=round(city_rng.uniform(0.62, 0.85), 4),
    )
    state.weather = Weather(
        temperature_c=region.temperature_c,
        precipitation_mm=round(city_rng.uniform(0.0, 3.0), 2),
        wind_kph=round(city_rng.uniform(4.0, 18.0), 2),
        cloud=round(city_rng.uniform(0.2, 0.8), 3),
        season="spring",
    )
    return state


class _BuildingCounter:
    __slots__ = ("value",)

    def __init__(self) -> None:
        self.value = 0

    def next_id(self) -> str:
        self.value += 1
        return make_building_id(self.value)


def _build_district(
    state: GeographyState,
    seeds: SeedTree,
    blueprint: DistrictBlueprint,
    total_residents: int,
    counter: _BuildingCounter,
    city: City,
) -> None:
    drng = seeds.district(blueprint.key)
    population = int(round(total_residents * blueprint.population_share))
    district = District(
        district_id=f"district_{blueprint.key}",
        city_id=city.city_id,
        name=blueprint.name,
        kind=blueprint.kind,
        area_km2=blueprint.area_km2,
        population=population,
        wealth_index=round(min(1.0, max(0.05, drng.normal(blueprint.wealth, 0.03))), 4),
        land_value_minor=int(round(blueprint.wealth * drng.uniform(180_000, 320_000))),
        pollution=round(max(0.0, drng.normal(blueprint.pollution, 0.02)), 4),
        crime_rate=round(max(0.001, drng.normal(blueprint.crime, 0.004)), 5),
        transport_capacity=round(
            drng.uniform(0.6, 1.0) * (1.3 if blueprint.kind is DistrictKind.COMMERCIAL else 1.0), 4
        ),
        service_coverage={
            "school": round(drng.uniform(0.4, 0.95), 3),
            "health": round(drng.uniform(0.35, 0.95), 3),
            "police": round(drng.uniform(0.3, 0.9), 3),
            "transit": round(drng.uniform(0.35, 0.95), 3),
        },
        coordinates=Coordinates(blueprint.x, blueprint.y),
    )
    state.districts[district.district_id] = district
    city.district_ids.append(district.district_id)

    def place(kind: BuildingKind, capacity: int, label: str, value_scale: float) -> None:
        bid = counter.next_id()
        state.buildings[bid] = Building(
            building_id=bid,
            kind=kind,
            district_id=district.district_id,
            name=label,
            capacity=capacity,
            condition=round(min(1.0, max(0.25, drng.normal(0.45 + 0.5 * blueprint.wealth, 0.12))), 4),
            value_minor=int(value_scale * district.land_value_minor),
            coordinates=Coordinates(
                round(blueprint.x + drng.uniform(-1.2, 1.2), 3),
                round(blueprint.y + drng.uniform(-1.2, 1.2), 3),
            ),
        )
        district.building_ids.append(bid)

    # Housing: roughly one block per 90 residents.
    blocks = max(4, population // 90)
    for i in range(blocks):
        place(BuildingKind.HOUSING, drng.randint(60, 140), f"{blueprint.name} Block {i + 1}", 2.4)

    workplace_plan: list[tuple[BuildingKind, int, tuple[int, int]]] = [
        (BuildingKind.RETAIL, max(2, population // 700), (15, 60))
    ]
    if blueprint.kind in (DistrictKind.COMMERCIAL, DistrictKind.ELITE, DistrictKind.MIXED):
        workplace_plan.append((BuildingKind.OFFICE, max(2, population // 500), (25, 120)))
    if blueprint.kind in (DistrictKind.INDUSTRIAL, DistrictKind.PORT, DistrictKind.PERIPHERY):
        workplace_plan.append((BuildingKind.FACTORY, max(2, population // 900), (40, 260)))
    for kind, count, (lo, hi) in workplace_plan:
        for _ in range(count):
            place(kind, drng.randint(lo, hi), f"{place_name(drng)} {kind.value.title()}", 1.6)


def _build_civic(state: GeographyState, seeds: SeedTree, counter: _BuildingCounter) -> None:
    civic_rng = seeds.city("city_hydra_civic")
    district_ids = list(state.districts)
    for kind, count, capacity, fixed_district in CIVIC_PLAN:
        for i in range(count):
            candidate = f"district_{fixed_district}" if fixed_district else ""
            district_id = candidate if candidate in state.districts else civic_rng.choice(district_ids)
            bid = counter.next_id()
            state.buildings[bid] = Building(
                building_id=bid,
                kind=kind,
                district_id=district_id,
                name=f"{place_name(civic_rng)} {kind.value.replace('_', ' ').title()}",
                capacity=capacity,
                condition=round(civic_rng.uniform(0.55, 0.98), 4),
                value_minor=int(civic_rng.uniform(1.5, 6.0) * 200_000),
                coordinates=state.districts[district_id].coordinates,
            )
            state.districts[district_id].building_ids.append(bid)


def _build_power(state: GeographyState, seeds: SeedTree, counter: _BuildingCounter, installed_mw: float) -> None:
    for plant_id, fuel, share, district_id, fuel_cost in PLANT_PLAN:
        plant_rng = seeds.rng("plant", plant_id)
        capacity_mw = round(installed_mw * share, 3)
        bid = counter.next_id()
        state.buildings[bid] = Building(
            building_id=bid,
            kind=BuildingKind.POWER_PLANT,
            district_id=district_id,
            name=f"{place_name(plant_rng)} Station",
            capacity=int(capacity_mw),
            condition=round(plant_rng.uniform(0.7, 0.98), 4),
            value_minor=int(capacity_mw * 900_000),
            coordinates=state.districts[district_id].coordinates,
        )
        state.districts[district_id].building_ids.append(bid)
        state.power_plants[plant_id] = PowerPlant(
            plant_id=plant_id,
            building_id=bid,
            fuel=fuel,
            capacity_mw=capacity_mw,
            output_mw=round(capacity_mw * plant_rng.uniform(0.72, 0.90), 3),
            availability=1.0,
            fuel_cost_per_mwh_minor=fuel_cost,
        )


def buildings_of_kind(state: GeographyState, district_id: str, kinds: tuple[BuildingKind, ...]) -> list[Building]:
    district = state.districts[district_id]
    return [state.buildings[b] for b in district.building_ids if state.buildings[b].kind in kinds]


def pick_building(rng: DeterministicRng, buildings: list[Building]) -> Building | None:
    available = [b for b in buildings if b.occupancy < b.capacity]
    if not available:
        return None
    return rng.choice(available)
