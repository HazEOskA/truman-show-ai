"""Demography: birth, ageing, illness, death and migration.

Run long enough and every founding resident is gone; the city is then populated entirely by
people the world produced itself. Individuals are simulated one by one, cohorts statistically,
and the two stay consistent because both draw on the same rates.
"""

from __future__ import annotations

from hydra.agents.model import Activity, AgentsState, Employment, Needs, Person, Personality, Sex, Tier
from hydra.companies.model import CompaniesState
from hydra.economy.model import EconomyState, OwnerKind
from hydra.events.importance import ImportanceInputs
from hydra.events.model import Topics
from hydra.geography.model import GeographyState
from hydra.kernel.clock import TICKS_PER_MONTH, TICKS_PER_YEAR
from hydra.kernel.ids import person_id as make_person_id
from hydra.kernel.systems import Phase, SystemSpec
from hydra.population.model import PopulationState
from hydra.social.model import Relation, SocialState

AGE_ORDER = ("0_17", "18_24", "25_34", "35_49", "50_64", "65_plus")
BAND_YEARS = {"0_17": 18, "18_24": 7, "25_34": 10, "35_49": 15, "50_64": 15, "65_plus": 25}


class DemographySystem:
    spec = SystemSpec(
        name="demographics",
        phase=Phase.SLOW,
        cadence_ticks=TICKS_PER_MONTH,
        priority=10,
        reads=("agents", "population", "geography", "economy", "companies"),
        writes=("agents", "population", "geography", "economy", "companies", "social"),
        emits=(Topics.PERSON_BIRTH, Topics.PERSON_DEATH, Topics.PERSON_MOVED),
        description="Monthly ageing, mortality, fertility and migration for individuals and cohorts.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        agents = ctx.state.domain(AgentsState)
        population = ctx.state.domain(PopulationState)
        geography = ctx.state.domain(GeographyState)
        economy = ctx.state.domain(EconomyState)
        companies = ctx.state.domain(CompaniesState)
        social = ctx.state.domain(SocialState)
        rng = ctx.rng("demography")

        births = 0
        deaths = 0
        month_fraction = 1.0 / 12.0

        for person_id in sorted(agents.people):
            person = agents.people[person_id]
            if not person.alive:
                continue
            person.age_years = round(person.age_years + month_fraction, 4)

            hazard = self._mortality(person)
            if rng.chance(hazard):
                self._die(ctx, person, agents, companies, population, social)
                deaths += 1
                continue

            if person.age_years >= 67 and person.employment in (Employment.EMPLOYED, Employment.PUBLIC):
                person.employment = Employment.RETIRED
                company = companies.companies.get(person.employer_id)
                if company and person.person_id in company.employee_ids:
                    company.employee_ids.remove(person.person_id)
                person.employer_id = ""
            if person.age_years >= 18 and person.employment is Employment.CHILD:
                person.employment = Employment.UNEMPLOYED

            if (
                20 <= person.age_years <= 42
                and person.sex is Sex.F
                and person.health > 0.6
                and rng.chance(self._fertility(person, economy))
            ):
                self._give_birth(ctx, person, agents, population, economy, social, rng)
                births += 1

        self._cohort_dynamics(ctx, agents, rng)
        self._migration(ctx, agents, geography, economy, rng)

        population.births_total += births
        population.deaths_total += deaths
        agents.births += births
        agents.deaths += deaths
        for district in geography.districts.values():
            district.population = sum(
                c.size for c in agents.cohorts.values() if c.district_id == district.district_id
            ) + sum(1 for p in agents.people.values() if p.alive and p.district_id == district.district_id)
        population.total_residents = agents.total_population()
        population.average_age = round(
            sum(p.age_years for p in agents.people.values() if p.alive) / max(1, len(agents.alive_people())), 3
        )
        ctx.telemetry.gauge("births_month", float(births))
        ctx.telemetry.gauge("deaths_month", float(deaths))
        ctx.telemetry.gauge("average_age", population.average_age)

    # -- individuals --------------------------------------------------------------
    @staticmethod
    def _mortality(person: Person) -> float:
        age = person.age_years
        base = 0.00004 + (max(0.0, age - 45) ** 2.6) * 1.1e-7
        health_penalty = (1.0 - person.health) * 0.004
        stress_penalty = person.stress * 0.0009
        return min(0.5, base + health_penalty + stress_penalty)

    @staticmethod
    def _fertility(person: Person, economy: EconomyState) -> float:
        base = 0.010
        prosperity = max(0.4, min(1.4, 1.2 - economy.unemployment_rate * 2.0))
        return base * prosperity * (0.6 + person.mood * 0.8)

    def _die(self, ctx, person: Person, agents: AgentsState, companies: CompaniesState,
             population: PopulationState, social: SocialState) -> None:  # noqa: ANN001
        person.alive = False
        person.death_tick = ctx.tick
        person.activity = Activity.OFFSCREEN
        company = companies.companies.get(person.employer_id)
        if company and person.person_id in company.employee_ids:
            company.employee_ids.remove(person.person_id)
        household = population.households.get(person.household_id)
        if household and person.person_id in household.member_ids:
            household.member_ids.remove(person.person_id)
        for edge in social.neighbours(person.person_id):
            edge.active = False
        ctx.emit(
            Topics.PERSON_DEATH,
            "died",
            actor=person.person_id,
            location=person.district_id,
            payload={"name": person.name, "age": round(person.age_years, 1), "occupation": person.occupation},
            inputs=ImportanceInputs(
                people_affected=1 + (12 if person.tier is Tier.PERSISTENT else 0),
                political_impact=0.3 if person.importance > 0.6 else 0.02,
                proximity=person.importance,
                novelty=0.3,
            ),
        )

    def _give_birth(self, ctx, mother: Person, agents: AgentsState, population: PopulationState,
                    economy: EconomyState, social: SocialState, rng) -> None:  # noqa: ANN001
        agents.next_person_index += 1
        person_id = make_person_id(agents.next_person_index)
        from hydra.genesis.names import full_name

        female = rng.chance(0.5)
        name_rng = ctx.stable_rng("birth", person_id)
        child = Person(
            person_id=person_id,
            name=f"{full_name(name_rng, female).split()[0]} {mother.name.split()[-1]}",
            tier=Tier.LIGHTWEIGHT,
            sex=Sex.F if female else Sex.M,
            birth_tick=ctx.tick,
            age_years=0.0,
            district_id=mother.district_id,
            household_id=mother.household_id,
            home_building_id=mother.home_building_id,
            location_building_id=mother.home_building_id,
            employment=Employment.CHILD,
            education=0.0,
            personality=Personality(
                openness=round(rng.clamped_normal(mother.personality.openness, 0.18, 0.02, 0.98), 4),
                conscientiousness=round(rng.clamped_normal(mother.personality.conscientiousness, 0.18, 0.02, 0.98), 4),
                extraversion=round(rng.clamped_normal(mother.personality.extraversion, 0.18, 0.02, 0.98), 4),
                agreeableness=round(rng.clamped_normal(mother.personality.agreeableness, 0.18, 0.02, 0.98), 4),
                neuroticism=round(rng.clamped_normal(mother.personality.neuroticism, 0.18, 0.02, 0.98), 4),
                risk_tolerance=round(rng.clamped_normal(0.5, 0.2, 0.02, 0.98), 4),
                ambition=round(rng.clamped_normal(0.5, 0.2, 0.02, 0.98), 4),
            ),
            needs=Needs(),
        )
        account = economy.open_account(person_id, OwnerKind.PERSON, balance_minor=0)
        child.account_id = account.account_id
        agents.people[person_id] = child
        agents.lightweight_ids.append(person_id)
        household = population.households.get(mother.household_id)
        if household is not None:
            household.member_ids.append(person_id)
            household.children += 1
            household.represented_people = len(household.member_ids)
        social.link(mother.person_id, person_id, Relation.FAMILY, tick=ctx.tick, strength=0.95, trust=0.95, sentiment=0.8)
        social.link(person_id, mother.person_id, Relation.FAMILY, tick=ctx.tick, strength=0.95, trust=0.95, sentiment=0.8)
        mother.mood = round(min(1.0, mother.mood + 0.1), 4)
        ctx.emit(
            Topics.PERSON_BIRTH,
            "born",
            actor=person_id,
            target=mother.person_id,
            location=mother.district_id,
            payload={"name": child.name},
            inputs=ImportanceInputs(people_affected=3, novelty=0.2, proximity=0.3),
        )

    # -- cohorts ------------------------------------------------------------------
    def _cohort_dynamics(self, ctx, agents: AgentsState, rng) -> None:  # noqa: ANN001
        annual = ctx.now.month == 1
        for cohort_id in sorted(agents.cohorts):
            cohort = agents.cohorts[cohort_id]
            if cohort.size <= 0:
                continue
            fertile = cohort.age_band in ("18_24", "25_34", "35_49")
            birth_rate = 0.0011 if fertile else 0.0
            death_rate = {"0_17": 0.00002, "18_24": 0.00004, "25_34": 0.00006,
                          "35_49": 0.00016, "50_64": 0.00055, "65_plus": 0.0032}[cohort.age_band]
            death_rate *= 2.0 - cohort.health
            cohort.births_accumulator += cohort.size * birth_rate * (0.7 + cohort.sentiment * 0.6)
            cohort.deaths_accumulator += cohort.size * death_rate
            born = int(cohort.births_accumulator)
            died = int(cohort.deaths_accumulator)
            cohort.births_accumulator -= born
            cohort.deaths_accumulator -= died
            cohort.size = max(0, cohort.size - died)

            if born:
                target_id = cohort_id.replace(cohort.age_band, "0_17")
                child_cohort = agents.cohorts.get(target_id)
                if child_cohort is not None:
                    child_cohort.size += born

            if annual:
                index = AGE_ORDER.index(cohort.age_band)
                if index < len(AGE_ORDER) - 1:
                    graduating = int(cohort.size / BAND_YEARS[cohort.age_band])
                    if graduating > 0:
                        next_id = cohort_id.replace(cohort.age_band, AGE_ORDER[index + 1])
                        next_cohort = agents.cohorts.get(next_id)
                        if next_cohort is not None:
                            cohort.size -= graduating
                            next_cohort.size += graduating

    def _migration(self, ctx, agents: AgentsState, geography: GeographyState, economy: EconomyState, rng) -> None:  # noqa: ANN001
        """People move towards work and away from unrest — within the city and beyond it."""

        for cohort_id in sorted(agents.cohorts):
            cohort = agents.cohorts[cohort_id]
            district = geography.districts.get(cohort.district_id)
            if district is None or cohort.size <= 0:
                continue
            pressure = (
                (1.0 - cohort.employment_rate) * 0.6
                + cohort.unrest * 0.5
                + district.pollution * 0.2
                - district.wealth_index * 0.3
            )
            cohort.migration_pressure = round(max(0.0, pressure), 5)
            if cohort.migration_pressure < 0.35 or not rng.chance(cohort.migration_pressure * 0.2):
                continue
            movers = int(cohort.size * 0.01 * cohort.migration_pressure)
            if movers <= 0:
                continue
            targets = [
                c for c in agents.cohorts.values()
                if c.age_band == cohort.age_band and c.income_band == cohort.income_band
                and c.district_id != cohort.district_id
            ]
            if not targets:
                continue
            target = max(targets, key=lambda c: (c.employment_rate - c.unrest, c.cohort_id))
            cohort.size -= movers
            target.size += movers
            ctx.emit(
                Topics.PERSON_MOVED,
                "migration",
                actor=cohort_id,
                target=target.cohort_id,
                location=cohort.district_id,
                payload={"movers": movers, "to": target.district_id, "pressure": cohort.migration_pressure},
                inputs=ImportanceInputs(people_affected=movers, political_impact=0.1),
            )
