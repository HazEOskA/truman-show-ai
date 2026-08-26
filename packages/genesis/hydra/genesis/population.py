"""Genesis of people: cohorts, households, individuals, jobs and first relationships.

The hybrid population is built top-down. Districts get demographic cohorts (Tier C), then a
slice of those cohorts is "resolved" into individually simulated people (Tier B), then the
world's notable roles are filled by persistent agents (Tier A). Nobody is hand-authored: the
mayor is a person drawn from the population who happens to hold an office.
"""

from __future__ import annotations

from dataclasses import dataclass

from hydra.agents.model import (
    AgentsState,
    Activity,
    Cohort,
    ComputeBudget,
    Employment,
    Goal,
    Needs,
    Person,
    Personality,
    Sex,
    Tier,
)
from hydra.companies.model import CompaniesState, Sector
from hydra.economy.model import EconomyState, OwnerKind
from hydra.geography.model import BuildingKind, GeographyState
from hydra.government.model import GovernmentState
from hydra.kernel.clock import TICKS_PER_YEAR
from hydra.kernel.config import WorldConfig
from hydra.kernel.ids import household_id as make_household_id
from hydra.kernel.ids import person_id as make_person_id
from hydra.kernel.rng import DeterministicRng
from hydra.media.model import MediaState
from hydra.memory.model import MemoryKind, MemoryState
from hydra.memory.operations import record as record_memory
from hydra.population.model import Household, PopulationState
from hydra.social.model import Relation, SocialState

from .names import full_name
from .seeds import SeedTree

AGE_BANDS: tuple[tuple[str, int, int, float], ...] = (
    ("0_17", 0, 17, 0.19),
    ("18_24", 18, 24, 0.10),
    ("25_34", 25, 34, 0.17),
    ("35_49", 35, 49, 0.22),
    ("50_64", 50, 64, 0.19),
    ("65_plus", 65, 92, 0.13),
)

INCOME_BANDS: tuple[tuple[str, float, float], ...] = (
    ("low", 0.36, 0.55),
    ("mid", 0.47, 1.0),
    ("high", 0.17, 2.1),
)

EDUCATION_BANDS = ("basic", "secondary", "tertiary")

BASE_MONTHLY_WAGE_MINOR = 320_000


@dataclass(slots=True)
class PopulationBuild:
    agents: AgentsState
    population: PopulationState
    social: SocialState
    memory: MemoryState


def build_population(
    seeds: SeedTree,
    config: WorldConfig,
    geography: GeographyState,
    economy: EconomyState,
    companies: CompaniesState,
    government: GovernmentState,
    media: MediaState,
) -> PopulationBuild:
    agents = AgentsState()
    population = PopulationState(total_residents=config.population.total_residents)
    social = SocialState()
    memory = MemoryState()

    _build_cohorts(seeds, config, geography, agents, economy)
    individuals = _build_individuals(seeds, config, geography, economy, agents, population, memory)
    _assign_jobs(seeds, config, geography, companies, agents, economy)
    _fill_cohort_employment(seeds, companies, agents, economy)
    _appoint_notables(seeds, agents, companies, government, media, memory)
    _wire_social_graph(seeds, agents, population, companies, social)
    population.district_population = {d: geography.districts[d].population for d in geography.districts}
    population.average_age = round(
        sum(p.age_years for p in individuals) / max(1, len(individuals)), 2
    )
    return PopulationBuild(agents=agents, population=population, social=social, memory=memory)


# ---------------------------------------------------------------------------------
# Tier C — cohorts
# ---------------------------------------------------------------------------------
def _build_cohorts(
    seeds: SeedTree,
    config: WorldConfig,
    geography: GeographyState,
    agents: AgentsState,
    economy: EconomyState,
) -> None:
    for district in geography.districts.values():
        for band, _lo, _hi, share in AGE_BANDS:
            for income_band, income_share, income_multiplier in INCOME_BANDS:
                cohort_id = f"cohort_{district.district_id[9:]}_{band}_{income_band}"
                rng = seeds.cohort(cohort_id)
                wealth_tilt = 0.6 + district.wealth_index * 0.9
                size = int(round(district.population * share * income_share * _income_tilt(income_band, wealth_tilt)))
                if size <= 0:
                    continue
                education = (
                    "tertiary" if income_band == "high" else "secondary" if income_band == "mid" else "basic"
                )
                employment_rate = (
                    0.0 if band == "0_17" else 0.0 if band == "65_plus" else round(min(0.99, rng.normal(0.93, 0.03)), 4)
                )
                cohort = Cohort(
                    cohort_id=cohort_id,
                    district_id=district.district_id,
                    age_band=band,
                    income_band=income_band,
                    education_band=education,
                    size=size,
                    employment_rate=employment_rate,
                    average_income_minor=int(
                        BASE_MONTHLY_WAGE_MINOR * income_multiplier * wealth_tilt * rng.uniform(0.85, 1.15)
                    ),
                    savings_minor=0,
                    consumption_propensity=round(
                        min(0.98, max(0.5, 1.05 - 0.22 * income_multiplier + rng.normal(0.0, 0.04))), 4
                    ),
                    health=round(min(0.99, max(0.4, rng.normal(0.88 - (0.18 if band == "65_plus" else 0.0), 0.05))), 4),
                    trust_government=round(min(0.95, max(0.05, rng.normal(0.5 + 0.12 * (district.wealth_index - 0.5), 0.12))), 4),
                    sentiment=round(min(0.95, max(0.05, rng.normal(0.55, 0.1))), 4),
                    unrest=round(max(0.0, rng.normal(0.06 + 0.12 * (1.0 - district.wealth_index), 0.02)), 4),
                )
                # A cohort holds its money in a real account, like anyone else: wages arrive
                # by transfer and purchases leave by transfer, so the city's money is
                # conserved whether a resident is simulated individually or statistically.
                savings = int(size * cohort.average_income_minor * rng.uniform(0.4, 2.4) / 30.0 * 30.0)
                account = economy.open_account(
                    cohort_id, OwnerKind.COHORT, balance_minor=savings, overdraft_minor=0
                )
                cohort.account_id = account.account_id
                cohort.savings_minor = savings
                agents.cohorts[cohort_id] = cohort


def _income_tilt(band: str, wealth_tilt: float) -> float:
    if band == "low":
        return max(0.3, 2.0 - wealth_tilt)
    if band == "high":
        return max(0.2, wealth_tilt - 0.3)
    return 1.0


# ---------------------------------------------------------------------------------
# Tier A/B — individuals
# ---------------------------------------------------------------------------------
def _build_individuals(
    seeds: SeedTree,
    config: WorldConfig,
    geography: GeographyState,
    economy: EconomyState,
    agents: AgentsState,
    population: PopulationState,
    memory: MemoryState,
) -> list[Person]:
    wanted = config.population.persistent_agents + config.population.lightweight_agents
    districts = list(geography.districts.values())
    weights = [d.population for d in districts]
    created: list[Person] = []
    household_rng = seeds.rng("households")

    while len(created) < wanted:
        district = household_rng.weighted_choice(districts, weights)
        household_size = max(1, int(round(household_rng.clamped_normal(config.population.household_size_mean, 1.1, 1, 6))))
        household_size = min(household_size, wanted - len(created))
        population.next_household_index += 1
        household_id = make_household_id(population.next_household_index)
        home = _pick_home(household_rng, geography, district.district_id)
        household = Household(
            household_id=household_id,
            district_id=district.district_id,
            building_id=home,
            savings_minor=int(household_rng.uniform(20_000, 3_400_000) * (0.4 + district.wealth_index)),
        )
        account = economy.open_account(
            household_id, OwnerKind.HOUSEHOLD, balance_minor=household.savings_minor, overdraft_minor=40_000
        )
        household.account_id = account.account_id
        household.housing_cost_minor = int(
            economy.markets["housing"].price_minor * (0.55 + district.wealth_index * 1.1) * (0.6 + 0.25 * household_size)
        )
        household.owns_home = household_rng.chance(0.25 + district.wealth_index * 0.35)
        if household.owns_home:
            household.mortgage_minor = int(household.housing_cost_minor * household_rng.uniform(40.0, 180.0))

        adults = 0
        for member_index in range(household_size):
            agents.next_person_index += 1
            index = agents.next_person_index
            prng = seeds.person(index)
            person_id = make_person_id(index)
            is_child = member_index >= 2 and prng.chance(0.65)
            age = _draw_age(prng, is_child)
            adults += 0 if age < 18 else 1
            sex = Sex.F if prng.chance(0.5) else Sex.M
            person = Person(
                person_id=person_id,
                name=full_name(prng, sex is Sex.F),
                tier=Tier.LIGHTWEIGHT,
                sex=sex,
                birth_tick=-int(age * TICKS_PER_YEAR),
                age_years=round(age, 2),
                district_id=district.district_id,
                household_id=household_id,
                home_building_id=home,
                location_building_id=home,
                education=round(min(1.0, max(0.05, prng.normal(0.3 + district.wealth_index * 0.5, 0.14))), 4),
                personality=Personality(
                    openness=round(prng.clamped_normal(0.5, 0.17, 0.02, 0.98), 4),
                    conscientiousness=round(prng.clamped_normal(0.5, 0.17, 0.02, 0.98), 4),
                    extraversion=round(prng.clamped_normal(0.5, 0.17, 0.02, 0.98), 4),
                    agreeableness=round(prng.clamped_normal(0.5, 0.17, 0.02, 0.98), 4),
                    neuroticism=round(prng.clamped_normal(0.5, 0.17, 0.02, 0.98), 4),
                    risk_tolerance=round(prng.clamped_normal(0.5, 0.2, 0.02, 0.98), 4),
                    ambition=round(prng.clamped_normal(0.5, 0.2, 0.02, 0.98), 4),
                ),
                values={
                    "security": round(prng.uniform(0.2, 0.9), 3),
                    "freedom": round(prng.uniform(0.2, 0.9), 3),
                    "fairness": round(prng.uniform(0.2, 0.9), 3),
                    "tradition": round(prng.uniform(0.1, 0.9), 3),
                    "achievement": round(prng.uniform(0.1, 0.9), 3),
                },
                needs=Needs(
                    food=round(prng.uniform(0.6, 0.95), 3),
                    rest=round(prng.uniform(0.5, 0.95), 3),
                    safety=round(min(0.98, max(0.1, prng.normal(0.5 + district.wealth_index * 0.4, 0.1))), 3),
                    social=round(prng.uniform(0.35, 0.9), 3),
                ),
                health=round(min(0.99, max(0.3, prng.normal(0.92 - max(0.0, (age - 45) * 0.004), 0.05))), 4),
                energy=round(prng.uniform(0.5, 0.95), 4),
                stress=round(min(0.95, max(0.02, prng.normal(0.28 + 0.18 * (1 - district.wealth_index), 0.1))), 4),
                mood=round(prng.clamped_normal(0.58, 0.12, 0.05, 0.95), 4),
                political_trust=round(prng.clamped_normal(0.5 + 0.1 * (district.wealth_index - 0.5), 0.16, 0.02, 0.98), 4),
                consumption_propensity=round(prng.clamped_normal(0.78, 0.08, 0.4, 0.98), 4),
                activity=Activity.ACTIVE,
            )
            person.skills = {
                "manual": round(prng.uniform(0.1, 0.9), 3),
                "technical": round(min(1.0, prng.uniform(0.05, 0.8) + person.education * 0.3), 3),
                "social": round(prng.uniform(0.1, 0.9), 3),
                "analytical": round(min(1.0, prng.uniform(0.05, 0.8) + person.education * 0.35), 3),
            }
            account = economy.open_account(
                person_id,
                OwnerKind.PERSON,
                balance_minor=int(prng.uniform(2_000, 900_000) * (0.4 + district.wealth_index)),
                overdraft_minor=20_000,
            )
            person.account_id = account.account_id
            person.employment = _initial_employment(age, prng)
            agents.people[person_id] = person
            agents.lightweight_ids.append(person_id)
            household.member_ids.append(person_id)
            if age < 18:
                household.children += 1
            created.append(person)
            if len(created) >= wanted:
                break

        household.represented_people = len(household.member_ids)
        population.households[household_id] = household
        building = geography.buildings.get(home)
        if building is not None:
            building.occupancy += len(household.member_ids)

    _promote_persistent(seeds, config, agents, memory)
    return created


def _pick_home(rng: DeterministicRng, geography: GeographyState, district_id: str) -> str:
    district = geography.districts[district_id]
    housing = [b for b in district.building_ids if geography.buildings[b].kind is BuildingKind.HOUSING]
    if not housing:
        return district.building_ids[0]
    free = [b for b in housing if geography.buildings[b].occupancy < geography.buildings[b].capacity]
    return rng.choice(free or housing)


def _draw_age(rng: DeterministicRng, is_child: bool) -> float:
    if is_child:
        return rng.uniform(0.5, 17.9)
    band = rng.weighted_choice(
        [b for b in AGE_BANDS if b[1] >= 18], [b[3] for b in AGE_BANDS if b[1] >= 18]
    )
    return rng.uniform(band[1], band[2])


def _initial_employment(age: float, rng: DeterministicRng) -> Employment:
    if age < 16:
        return Employment.CHILD
    if age < 24 and rng.chance(0.55):
        return Employment.STUDENT
    if age >= 66:
        return Employment.RETIRED
    return Employment.UNEMPLOYED


def _promote_persistent(seeds: SeedTree, config: WorldConfig, agents: AgentsState, memory: MemoryState) -> None:
    """Pick the persistent cast: adults with the highest latent salience."""

    rng = seeds.rng("tier_a")
    adults = [p for p in agents.people.values() if p.age_years >= 22]
    scored = sorted(
        adults,
        key=lambda p: (
            -(p.personality.ambition * 0.5 + p.education * 0.3 + p.personality.extraversion * 0.2),
            p.person_id,
        ),
    )
    for person in scored[: config.population.persistent_agents]:
        person.tier = Tier.PERSISTENT
        person.importance = round(rng.uniform(0.3, 0.6), 4)
        person.compute = ComputeBudget(
            llm_calls_per_day=config.llm.daily_calls_per_agent,
            token_budget=config.llm.token_budget_per_agent,
            reasoning_budget=120,
            priority=round(rng.uniform(0.4, 0.9), 4),
        )
        agents.persistent_ids.append(person.person_id)
        if person.person_id in agents.lightweight_ids:
            agents.lightweight_ids.remove(person.person_id)
        record_memory(
            memory,
            person.person_id,
            tick=0,
            topic="identity",
            summary=f"{person.name}, lives in {person.district_id}",
            kind=MemoryKind.SEMANTIC,
            salience=0.9,
            source="genesis",
        )
    agents.persistent_ids.sort()


# ---------------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------------
WORK_HOURS_PER_DAY = 7.0


def labour_requirement_hours(company, economy: EconomyState) -> float:
    """Daily labour hours a firm needs to run at its planned output."""

    recipe = economy.recipes.get(company.recipe_code)
    if recipe is None:
        return company.capacity_units * 0.02
    return company.capacity_units * company.utilisation * recipe.labour_hours


def staffing_target(company, economy: EconomyState) -> int:
    return max(1, int(round(labour_requirement_hours(company, economy) / WORK_HOURS_PER_DAY)))


def _assign_jobs(
    seeds: SeedTree,
    config: WorldConfig,
    geography: GeographyState,
    companies: CompaniesState,
    agents: AgentsState,
    economy: EconomyState,
) -> None:
    rng = seeds.rng("labour")
    firms = companies.active()
    if not firms:
        return
    for company in firms:
        company.headcount_target = staffing_target(company, economy)
    by_district: dict[str, list] = {}
    for company in firms:
        by_district.setdefault(company.district_id, []).append(company)

    for person in agents.people.values():
        if person.employment not in (Employment.UNEMPLOYED,):
            continue
        if person.age_years < 18 or person.age_years > 66:
            continue
        if rng.chance(0.055):          # structural unemployment at genesis
            continue
        local = [c for c in by_district.get(person.district_id, []) if c.headcount() < c.headcount_target]
        hiring = [c for c in firms if c.headcount() < c.headcount_target]
        if not hiring:
            break
        pool = local if local and rng.chance(0.62) else hiring
        company = rng.choice(pool)
        person.employer_id = company.company_id
        person.employment = Employment.EMPLOYED
        person.work_building_id = company.building_id
        skill_key = _sector_skill(company.sector)
        skill = person.skills.get(skill_key, 0.5)
        person.wage_minor = int(
            company.average_wage_minor * (0.72 + 0.55 * skill) * rng.uniform(0.9, 1.12)
        )
        person.occupation = _occupation_label(company.sector, skill)
        company.employee_ids.append(person.person_id)


def _sector_skill(sector: Sector) -> str:
    if sector in (Sector.TECH, Sector.ELECTRONICS, Sector.FINANCE, Sector.EDUCATION, Sector.HEALTHCARE, Sector.MEDIA):
        return "analytical"
    if sector in (Sector.SERVICES, Sector.RETAIL):
        return "social"
    if sector in (Sector.ENERGY, Sector.WATER, Sector.MANUFACTURING):
        return "technical"
    return "manual"


def _occupation_label(sector: Sector, skill: float) -> str:
    ladder = {
        Sector.ENERGY: ("plant operator", "grid engineer"),
        Sector.WATER: ("water technician", "hydraulics engineer"),
        Sector.AGRICULTURE: ("farmhand", "agronomist"),
        Sector.FOOD: ("food worker", "process engineer"),
        Sector.MANUFACTURING: ("machine operator", "production engineer"),
        Sector.ELECTRONICS: ("assembler", "electronics engineer"),
        Sector.CONSTRUCTION: ("builder", "site manager"),
        Sector.LOGISTICS: ("driver", "logistics planner"),
        Sector.RETAIL: ("shop assistant", "store manager"),
        Sector.SERVICES: ("service worker", "consultant"),
        Sector.FINANCE: ("clerk", "analyst"),
        Sector.HEALTHCARE: ("care worker", "physician"),
        Sector.EDUCATION: ("teaching assistant", "teacher"),
        Sector.MEDIA: ("production assistant", "journalist"),
        Sector.TECH: ("technician", "software engineer"),
    }
    low, high = ladder.get(sector, ("worker", "specialist"))
    return high if skill > 0.62 else low


def _fill_cohort_employment(
    seeds: SeedTree, companies: CompaniesState, agents: AgentsState, economy: EconomyState
) -> None:
    """Firms are mostly staffed by cohort members; individuals are the visible minority.

    Staffing follows each firm's labour requirement, not its unit capacity: a power plant
    measured in kWh and a bakery measured in baskets are not comparable in units, only in
    hours of work.
    """

    rng = seeds.rng("cohort_labour")
    firms = companies.active()
    if not firms:
        return
    working_cohorts = [c for c in agents.cohorts.values() if c.employment_rate > 0.0]
    working_cohorts.sort(key=lambda c: c.cohort_id)
    total_workers = sum(int(c.size * c.employment_rate) for c in working_cohorts)
    if total_workers <= 0:
        return

    vacancies: list[tuple[object, int]] = []
    for company in firms:
        gap = company.headcount_target - company.headcount()
        if gap > 0:
            vacancies.append((company, gap))
    if not vacancies:
        companies.total_employment = sum(c.headcount() for c in firms)
        return

    total_gap = sum(gap for _, gap in vacancies)
    unplaced = min(total_workers - sum(1 for p in agents.people.values() if p.employer_id), total_gap)
    for company, gap in vacancies:
        allocation = int(round(unplaced * gap / max(1, total_gap)))
        placed = 0
        while placed < allocation and working_cohorts:
            cohort = rng.weighted_choice(
                working_cohorts,
                [max(1.0, c.size * c.employment_rate) * (2.0 if c.district_id == company.district_id else 1.0)
                 for c in working_cohorts],
            )
            chunk = min(allocation - placed, max(1, int(gap / 6) + rng.randint(1, 12)))
            company.cohort_employees[cohort.cohort_id] = company.cohort_employees.get(cohort.cohort_id, 0) + chunk
            placed += chunk
    companies.total_employment = sum(c.headcount() for c in firms)


# ---------------------------------------------------------------------------------
# Notable roles
# ---------------------------------------------------------------------------------
def _appoint_notables(
    seeds: SeedTree,
    agents: AgentsState,
    companies: CompaniesState,
    government: GovernmentState,
    media: MediaState,
    memory: MemoryState,
) -> None:
    rng = seeds.rng("notables")
    pool = [agents.people[i] for i in agents.persistent_ids if agents.people[i].age_years >= 28]
    pool.sort(key=lambda p: p.person_id)
    cursor = 0

    def take() -> Person | None:
        nonlocal cursor
        while cursor < len(pool):
            person = pool[cursor]
            cursor += 1
            if not person.traits:
                return person
        return None

    def appoint(person: Person | None, occupation: str, trait: str, importance: float, wage: int) -> Person | None:
        if person is None:
            return None
        person.occupation = occupation
        person.traits.append(trait)
        person.importance = round(min(1.0, importance + rng.uniform(-0.05, 0.05)), 4)
        person.wage_minor = wage
        person.employment = Employment.PUBLIC if trait.startswith("gov") else person.employment
        record_memory(
            memory,
            person.person_id,
            tick=0,
            topic="role",
            summary=f"holds the role of {occupation}",
            kind=MemoryKind.SEMANTIC,
            salience=0.95,
            source="genesis",
        )
        return person

    mayor = appoint(take(), "mayor", "gov_mayor", 0.95, 780_000)
    if mayor is not None:
        government.mayor_id = mayor.person_id
        government.institutions["gov_city"].leader_id = mayor.person_id
        mayor.goals.append(Goal(goal_id=f"{mayor.person_id}_g1", label="hold the city together", kind="hold_power", priority=0.9))

    for institution_id, occupation, trait, importance, wage in (
        ("gov_council", "council speaker", "gov_council", 0.72, 520_000),
        ("gov_police", "police chief", "gov_police", 0.7, 560_000),
        ("gov_court", "chief judge", "gov_court", 0.68, 620_000),
        ("gov_central_bank", "central bank governor", "gov_bank", 0.8, 840_000),
        ("gov_regulator", "utilities regulator", "gov_regulator", 0.62, 480_000),
        ("gov_services", "services director", "gov_services", 0.6, 500_000),
    ):
        person = appoint(take(), occupation, trait, importance, wage)
        if person is not None:
            government.institutions[institution_id].leader_id = person.person_id

    for party in sorted(government.parties.values(), key=lambda p: p.party_id):
        leader = appoint(take(), f"leader of {party.name}", "politician", 0.66, 460_000)
        if leader is not None:
            party.leader_id = leader.person_id

    largest = sorted(companies.active(), key=lambda c: (-c.capacity_units, c.company_id))[:18]
    for company in largest:
        ceo = appoint(take(), f"CEO of {company.name}", "ceo", 0.68, max(900_000, company.average_wage_minor * 4))
        if ceo is None:
            break
        ceo.employer_id = company.company_id
        ceo.employment = Employment.EMPLOYED
        company.owner_ids.append(ceo.person_id)
        if ceo.person_id not in company.employee_ids:
            company.employee_ids.append(ceo.person_id)

    for outlet in sorted(media.outlets.values(), key=lambda o: o.outlet_id):
        editor = appoint(take(), f"editor at {outlet.name}", "journalist", 0.6, 420_000)
        if editor is not None:
            outlet.owner_ids.append(editor.person_id)
            outlet.sources.append(editor.person_id)
        reporter = appoint(take(), f"reporter at {outlet.name}", "journalist", 0.45, 300_000)
        if reporter is not None:
            outlet.sources.append(reporter.person_id)

    for _ in range(8):
        appoint(take(), "researcher", "scientist", 0.5, 480_000)
    for _ in range(6):
        appoint(take(), "union organiser", "activist", 0.52, 260_000)
    for _ in range(4):
        appoint(take(), "physician", "doctor", 0.45, 640_000)
    for _ in range(4):
        appoint(take(), "investor", "investor", 0.55, 1_200_000)


# ---------------------------------------------------------------------------------
# Social graph
# ---------------------------------------------------------------------------------
def _wire_social_graph(
    seeds: SeedTree,
    agents: AgentsState,
    population: PopulationState,
    companies: CompaniesState,
    social: SocialState,
) -> None:
    rng = seeds.rng("social")

    for household in population.households.values():
        members = household.member_ids
        for i, source in enumerate(members):
            for target in members[i + 1 :]:
                for a, b in ((source, target), (target, source)):
                    edge = social.link(a, b, Relation.FAMILY, tick=0, strength=0.85, trust=0.85, sentiment=0.5)
                    edge.interactions = rng.randint(50, 400)

    by_building: dict[str, list[str]] = {}
    for household in population.households.values():
        by_building.setdefault(household.building_id, []).extend(household.member_ids)
    for neighbours in by_building.values():
        if len(neighbours) < 2:
            continue
        for person_id in neighbours:
            for other in rng.sample([n for n in neighbours if n != person_id], min(3, len(neighbours) - 1)):
                social.link(person_id, other, Relation.NEIGHBOUR, tick=0,
                            strength=round(rng.uniform(0.1, 0.5), 3),
                            trust=round(rng.uniform(0.2, 0.7), 3),
                            sentiment=round(rng.uniform(-0.1, 0.5), 3))

    for company in companies.active():
        staff = company.employee_ids
        for person_id in staff:
            person = agents.people.get(person_id)
            if person is None:
                continue
            social.link(person_id, company.company_id, Relation.WORKS_FOR, tick=0,
                        strength=0.6, trust=round(rng.uniform(0.3, 0.8), 3), sentiment=round(rng.uniform(-0.2, 0.6), 3))
            for other in rng.sample([s for s in staff if s != person_id], min(4, max(0, len(staff) - 1))):
                social.link(person_id, other, Relation.COLLEAGUE, tick=0,
                            strength=round(rng.uniform(0.15, 0.6), 3),
                            trust=round(rng.uniform(0.25, 0.75), 3),
                            sentiment=round(rng.uniform(-0.15, 0.55), 3))

    notables = [agents.people[i] for i in agents.persistent_ids if agents.people[i].traits]
    for person in notables:
        for other in rng.sample([n for n in notables if n.person_id != person.person_id], min(6, max(0, len(notables) - 1))):
            relation = Relation.ALLY if rng.chance(0.6) else Relation.COMPETITOR
            social.link(person.person_id, other.person_id, relation, tick=0,
                        strength=round(rng.uniform(0.2, 0.75), 3),
                        trust=round(rng.uniform(0.15, 0.8), 3),
                        sentiment=round(rng.uniform(-0.5, 0.7), 3))
