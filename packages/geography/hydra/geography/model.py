"""Physical world: planet → continent → country → region → city → district → building.

Geography is not scenery. Every layer here is read by other subsystems: districts feed the
housing and labour markets, infrastructure feeds production and prices, pollution and
transport feed health and behaviour.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import ClassVar

from hydra.kernel.state import DomainState, register_domain


class DistrictKind(str, enum.Enum):
    RESIDENTIAL = "residential"
    INDUSTRIAL = "industrial"
    COMMERCIAL = "commercial"
    MIXED = "mixed"
    PERIPHERY = "periphery"
    ELITE = "elite"
    PORT = "port"


class BuildingKind(str, enum.Enum):
    HOUSING = "housing"
    OFFICE = "office"
    FACTORY = "factory"
    RETAIL = "retail"
    SCHOOL = "school"
    UNIVERSITY = "university"
    HOSPITAL = "hospital"
    POLICE = "police"
    COURT = "court"
    CITY_HALL = "city_hall"
    POWER_PLANT = "power_plant"
    WATER_PLANT = "water_plant"
    DATA_CENTRE = "data_centre"
    TRANSPORT_HUB = "transport_hub"
    CULTURE = "culture"


class Climate(str, enum.Enum):
    TEMPERATE = "temperate"
    CONTINENTAL = "continental"
    ARID = "arid"
    OCEANIC = "oceanic"
    SUBTROPICAL = "subtropical"


@dataclass(slots=True)
class Coordinates:
    x: float = 0.0
    y: float = 0.0


@dataclass(slots=True)
class Building:
    building_id: str
    kind: BuildingKind
    district_id: str
    name: str = ""
    capacity: int = 0
    occupancy: int = 0
    condition: float = 1.0
    value_minor: int = 0
    owner_id: str = ""
    built_tick: int = 0
    coordinates: Coordinates = field(default_factory=Coordinates)


@dataclass(slots=True)
class PowerPlant:
    plant_id: str
    building_id: str
    fuel: str                      # fission | gas | solar | wind | hydro
    capacity_mw: float
    output_mw: float
    availability: float = 1.0      # 0..1, damage/maintenance multiplier
    operator_id: str = ""
    fuel_cost_per_mwh_minor: int = 0


@dataclass(slots=True)
class Infrastructure:
    power_capacity_mw: float = 0.0
    power_output_mw: float = 0.0
    power_demand_mw: float = 0.0
    water_capacity_m3: float = 0.0
    water_output_m3: float = 0.0
    road_capacity: float = 0.0
    road_load: float = 0.0
    net_capacity_gbps: float = 0.0
    net_load_gbps: float = 0.0
    condition: float = 1.0
    maintenance_backlog_minor: int = 0


@dataclass(slots=True)
class District:
    district_id: str
    city_id: str
    name: str
    kind: DistrictKind
    area_km2: float
    population: int = 0
    wealth_index: float = 0.5          # 0 poorest .. 1 richest
    land_value_minor: int = 0
    pollution: float = 0.1
    crime_rate: float = 0.02
    unrest: float = 0.05
    service_coverage: dict[str, float] = field(default_factory=dict)
    transport_capacity: float = 1.0
    transport_load: float = 0.0
    power_reliability: float = 1.0
    building_ids: list[str] = field(default_factory=list)
    coordinates: Coordinates = field(default_factory=Coordinates)


@dataclass(slots=True)
class City:
    city_id: str
    name: str
    region_id: str
    founded_year: int = 0
    district_ids: list[str] = field(default_factory=list)
    infrastructure: Infrastructure = field(default_factory=Infrastructure)
    coordinates: Coordinates = field(default_factory=Coordinates)
    is_capital: bool = False


@dataclass(slots=True)
class Region:
    """Spec section 6 record."""

    region_id: str
    country_id: str
    name: str
    population: int = 0
    area_km2: float = 0.0
    climate: Climate = Climate.TEMPERATE
    temperature_c: float = 11.0
    water: float = 1.0              # availability index
    food: float = 1.0
    energy: float = 1.0
    resources: dict[str, float] = field(default_factory=dict)
    infrastructure: float = 0.6
    industry: float = 0.5
    wealth: float = 0.5
    technology: float = 0.5
    pollution: float = 0.15
    political_stability: float = 0.7
    transport_capacity: float = 0.7
    city_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Country:
    country_id: str
    name: str
    continent_id: str
    capital_city_id: str = ""
    region_ids: list[str] = field(default_factory=list)
    currency_code: str = "HYD"
    government_id: str = ""


@dataclass(slots=True)
class Continent:
    continent_id: str
    name: str
    area_km2: float
    country_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Planet:
    planet_id: str
    name: str
    radius_km: float
    axial_tilt_deg: float
    year_days: int
    continent_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Weather:
    temperature_c: float = 11.0
    precipitation_mm: float = 0.0
    wind_kph: float = 8.0
    cloud: float = 0.4
    season: str = "spring"
    heat_stress: float = 0.0
    cold_stress: float = 0.0


@register_domain
@dataclass(slots=True)
class GeographyState(DomainState):
    DOMAIN: ClassVar[str] = "geography"

    planet: Planet | None = None
    continents: dict[str, Continent] = field(default_factory=dict)
    countries: dict[str, Country] = field(default_factory=dict)
    regions: dict[str, Region] = field(default_factory=dict)
    cities: dict[str, City] = field(default_factory=dict)
    districts: dict[str, District] = field(default_factory=dict)
    buildings: dict[str, Building] = field(default_factory=dict)
    power_plants: dict[str, PowerPlant] = field(default_factory=dict)
    weather: Weather = field(default_factory=Weather)
    seed_city_id: str = ""

    # -- convenience --------------------------------------------------------------
    def city(self) -> City:
        return self.cities[self.seed_city_id]

    def city_districts(self, city_id: str) -> list[District]:
        return [self.districts[d] for d in self.cities[city_id].district_ids]

    def district_of(self, building_id: str) -> District | None:
        building = self.buildings.get(building_id)
        return self.districts.get(building.district_id) if building else None
