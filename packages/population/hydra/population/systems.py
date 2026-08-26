"""Consumption: households buy hour by hour, cohorts are settled once a day.

Households are the demand side of every market. Their spending is where a price rise turns
into a cut in living standards, and where a lost job turns into a fall in city-wide demand.
"""

from __future__ import annotations

from hydra.agents.model import AgentsState, Employment
from hydra.economy.clearing import purchase
from hydra.economy.demand import (
    BATCH,
    BATCH_HOUR,
    COMMUTE_HOURS,
    COMMUTE_TRIPS_PER_WORKER,
    CONTINUOUS,
    DAILY_PER_RESIDENT,
    MEAL_HOURS,
    price_response,
)
from hydra.economy.model import EconomyState
from hydra.economy.money import transfer
from hydra.events.importance import ImportanceInputs
from hydra.events.model import Topics, Visibility
from hydra.companies.model import CompaniesState, Sector
from hydra.geography.model import BuildingKind, GeographyState
from hydra.government.model import GovernmentState
from hydra.kernel.clock import TICKS_PER_DAY, TICKS_PER_HOUR
from hydra.kernel.systems import Phase, SystemSpec

SAVINGS_RATE = 0.02            # share of income households keep back
NEWS_DECAY_PER_DAY = 0.80      # yesterday's headlines matter less than today's

from .model import PopulationState



class HouseholdConsumptionSystem:
    spec = SystemSpec(
        name="household_consumption",
        phase=Phase.PHYSICAL,
        cadence_ticks=TICKS_PER_HOUR,
        priority=40,
        reads=("population", "agents", "economy", "geography", "government"),
        writes=("population", "agents", "economy", "government"),
        emits=(Topics.ECON_TRADE,),
        description="Hourly household purchases at the world's physical consumption rates.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        population = ctx.state.domain(PopulationState)
        agents = ctx.state.domain(AgentsState)
        economy = ctx.state.domain(EconomyState)
        government = ctx.state.domain(GovernmentState)
        geography = ctx.state.domain(GeographyState)
        now = ctx.now
        vat = government.vat_rate
        treasury = government.treasury_account_id
        hungry = 0
        spend_total = 0

        for household_id in sorted(population.households):
            household = population.households[household_id]
            people = [
                agents.people[p] for p in household.member_ids
                if p in agents.people and agents.people[p].alive
            ]
            if not people:
                continue
            size = len(people)
            commuters = sum(1 for p in people if p.employment in (Employment.EMPLOYED, Employment.PUBLIC))
            district = geography.districts[household.district_id]

            basket: list[tuple[str, float, bool]] = []
            for code in CONTINUOUS:
                quantity = DAILY_PER_RESIDENT[code] * size / 24.0
                if code == "electricity":
                    quantity *= (1.2 if 17 <= now.hour <= 22 else 0.9) * district.power_reliability
                basket.append((code, quantity, False))
            if now.hour in MEAL_HOURS:
                basket.append(("food", DAILY_PER_RESIDENT["food"] * size / len(MEAL_HOURS), True))
            if now.hour in COMMUTE_HOURS:
                trips = commuters * COMMUTE_TRIPS_PER_WORKER / len(COMMUTE_HOURS)
                trips += DAILY_PER_RESIDENT["transport"] * size / 24.0
                if trips > 0:
                    basket.append(("transport", trips, False))
            if now.hour == 0:
                household.daily_spend_minor = 0
                household.daily_income_minor = sum(
                    int(p.wage_minor / 30.0) for p in people
                ) or int(government.welfare_per_day_minor * size * 0.6)

            if now.hour == BATCH_HOUR:
                propensity = sum(p.consumption_propensity for p in people) / size
                for code in BATCH:
                    basket.append((code, DAILY_PER_RESIDENT[code] * size * propensity, code == "consumer_goods"))

            for code, quantity, importable in basket:
                quantity = price_response(economy, code, quantity)
                if quantity <= 0.0:
                    continue
                economy.markets[code].demand += quantity
                bought = purchase(
                    economy,
                    buyer_account_id=household.account_id,
                    code=code,
                    quantity=quantity,
                    vat_rate=vat,
                    treasury_account_id=treasury,
                    allow_import=importable,
                )
                household.monthly_spend_minor += bought.spent_minor + bought.tax_minor
                spend_total += bought.spent_minor + bought.tax_minor
                household.daily_spend_minor += bought.spent_minor + bought.tax_minor
                if code == "food":
                    household.food_stock = round(max(0.0, household.food_stock + bought.filled - quantity), 4)
                    if bought.filled < quantity * 0.7:
                        hungry += size
                        for person in people:
                            person.needs.food = round(max(0.0, person.needs.food - 0.08), 4)
                            person.stress = round(min(1.0, person.stress + 0.03), 4)
                    else:
                        for person in people:
                            person.needs.food = round(min(1.0, person.needs.food + 0.12), 4)

        # Whatever a household has not spent on necessities by the evening is discretionary
        # income. Recycling it is what keeps wages and revenue in the same universe — an
        # economy where every wage is saved is an economy where every firm goes bankrupt.
        if now.hour == BATCH_HOUR + 1:
            for household_id in sorted(population.households):
                household = population.households[household_id]
                spare = int((household.daily_income_minor - household.daily_spend_minor) * (1.0 - SAVINGS_RATE))
                if spare <= 0:
                    continue
                for code, share in (("services", 0.5), ("consumer_goods", 0.3), ("healthcare", 0.12), ("education", 0.08)):
                    price = economy.markets[code].price_minor
                    quantity = (spare * share) / max(1, price)
                    if quantity <= 0.0:
                        continue
                    economy.markets[code].demand += quantity
                    bought = purchase(
                        economy,
                        buyer_account_id=household.account_id,
                        code=code,
                        quantity=quantity,
                        vat_rate=vat,
                        treasury_account_id=treasury,
                        allow_import=code == "consumer_goods",
                    )
                    household.daily_spend_minor += bought.spent_minor + bought.tax_minor
                    household.monthly_spend_minor += bought.spent_minor + bought.tax_minor
                    spend_total += bought.spent_minor + bought.tax_minor

        ctx.telemetry.gauge("hungry_people", float(hungry))
        ctx.telemetry.gauge("household_spend_minor", float(spend_total))
        ctx.telemetry.gauge("households", float(len(population.households)))


class HousingSystem:
    """Dwellings, rent and arrears.

    Rent is not a production cost, it is scarcity: the price follows the ratio of dwellings to
    households. Construction feeds that ratio by finishing buildings, which is why building
    more is the only thing that actually brings rent down.
    """

    spec = SystemSpec(
        name="housing",
        phase=Phase.INSTITUTIONS,
        cadence_ticks=TICKS_PER_DAY,
        priority=50,
        reads=("population", "economy", "geography", "government", "agents", "companies"),
        writes=("population", "economy", "agents", "government", "geography", "companies"),
        emits=(Topics.PERSON_MOVED,),
        description="Dwelling stock, monthly rent, arrears and eviction pressure.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        population = ctx.state.domain(PopulationState)
        economy = ctx.state.domain(EconomyState)
        government = ctx.state.domain(GovernmentState)
        agents = ctx.state.domain(AgentsState)
        geography = ctx.state.domain(GeographyState)
        companies = ctx.state.domain(CompaniesState)
        market = economy.markets["housing"]

        # 1. Finished construction becomes real dwelling capacity.
        for company in companies.by_sector(Sector.CONSTRUCTION):
            finished = int(company.inventory.get("housing", 0.0))
            if finished <= 0:
                continue
            company.inventory["housing"] = round(company.inventory.get("housing", 0.0) - finished, 4)
            district = geography.districts.get(company.district_id)
            if district is None:
                continue
            homes = [
                geography.buildings[b] for b in district.building_ids
                if geography.buildings[b].kind is BuildingKind.HOUSING
            ]
            if homes:
                homes[ctx.tick % len(homes)].capacity += finished
                company.supplied_window += finished

        # 2. Price the rental market: dwellings against households.
        dwellings = sum(
            b.capacity for b in geography.buildings.values() if b.kind is BuildingKind.HOUSING
        )
        households = len(population.households)
        cohort_households = max(1, int(agents.cohort_population() / max(1.2, ctx.config.population.household_size_mean)))
        seats = max(1, int(dwellings / max(1.2, ctx.config.population.household_size_mean)))
        market.supply = seats / 30.0
        market.demand = (households + cohort_households) / 30.0

        # 3. Rent, once a simulated month.
        if ctx.now.day != 1:
            return
        evictions = 0
        for household_id in sorted(population.households):
            household = population.households[household_id]
            cost = int(market.price_minor * (0.7 + 0.3 * household.represented_people))
            household.housing_cost_minor = cost
            target = economy.escrow_account_id
            if transfer(economy, household.account_id, target, cost):
                household.arrears_minor = max(0, household.arrears_minor - cost // 4)
                household.evicted = False
            else:
                household.arrears_minor += cost
                for person_id in household.member_ids:
                    person = agents.people.get(person_id)
                    if person is not None:
                        person.stress = round(min(1.0, person.stress + 0.08), 4)
                        person.needs.safety = round(max(0.0, person.needs.safety - 0.07), 4)
                if household.arrears_minor > cost * 3:
                    household.evicted = True
                    evictions += 1
            household.monthly_spend_minor = 0

        population.homelessness = sum(1 for h in population.households.values() if h.evicted)
        if evictions:
            ctx.emit(
                Topics.PERSON_MOVED,
                "evictions",
                payload={"count": evictions, "rent_minor": market.price_minor},
                inputs=ImportanceInputs(
                    people_affected=evictions * 2.4,
                    economic_impact=evictions * market.price_minor,
                    political_impact=0.4,
                    risk=0.35,
                ),
            )


class CohortConsumptionSystem:
    """Tier C, settled hour by hour for what people use continuously and once a day for the rest.

    Splitting the two matters physically: a whole day of a district's electricity dropped into
    a single hour would make the grid think it had to serve twenty-four times the load.
    """

    spec = SystemSpec(
        name="cohort_consumption",
        phase=Phase.PHYSICAL,
        cadence_ticks=TICKS_PER_HOUR,
        priority=45,
        reads=("agents", "economy", "geography", "government"),
        writes=("agents", "economy", "government", "geography"),
        emits=(Topics.PERSON_PROTEST,),
        description="Aggregate consumption, welfare, sentiment and unrest for the cohort population.",
    )

    SETTLE_HOUR = 2

    def step(self, ctx) -> None:  # noqa: ANN001
        agents = ctx.state.domain(AgentsState)
        economy = ctx.state.domain(EconomyState)
        government = ctx.state.domain(GovernmentState)
        now = ctx.now
        vat = government.vat_rate
        treasury = government.treasury_account_id

        for cohort_id in sorted(agents.cohorts):
            cohort = agents.cohorts[cohort_id]
            if cohort.size <= 0 or not cohort.account_id:
                continue
            self._hourly_basket(ctx, cohort, economy, government, now, vat, treasury)

        if now.hour == self.SETTLE_HOUR:
            self._daily_settlement(ctx, agents, economy, government)

    # -- hourly -------------------------------------------------------------------
    @staticmethod
    def _hourly_basket(ctx, cohort, economy, government, now, vat, treasury) -> None:  # noqa: ANN001
        basket: list[tuple[str, float, bool]] = []
        for code in CONTINUOUS:
            basket.append((code, DAILY_PER_RESIDENT[code] * cohort.size / 24.0, False))
        if now.hour in MEAL_HOURS:
            basket.append(("food", DAILY_PER_RESIDENT["food"] * cohort.size / len(MEAL_HOURS), True))
        if now.hour in COMMUTE_HOURS:
            workers = cohort.size * cohort.employment_rate
            trips = workers * COMMUTE_TRIPS_PER_WORKER / len(COMMUTE_HOURS)
            trips += DAILY_PER_RESIDENT["transport"] * cohort.size / 24.0
            basket.append(("transport", trips, False))

        for code, quantity, importable in basket:
            quantity = price_response(economy, code, quantity)
            if quantity <= 0.0:
                continue
            economy.markets[code].demand += quantity
            bought = purchase(
                economy,
                buyer_account_id=cohort.account_id,
                code=code,
                quantity=quantity,
                vat_rate=vat,
                treasury_account_id=treasury,
                allow_import=importable,
            )
            government.revenue_ytd_minor += bought.tax_minor
            if code == "food" and bought.filled < quantity * 0.75:
                cohort.health = round(max(0.3, cohort.health - 0.002), 5)

    # -- daily --------------------------------------------------------------------
    def _daily_settlement(self, ctx, agents, economy, government) -> None:  # noqa: ANN001
        vat = government.vat_rate
        treasury = government.treasury_account_id
        geography = ctx.state.domain(GeographyState)
        rng = ctx.rng("cohort_settlement")

        essentials = ("food", "electricity", "water", "transport")
        basket_cost = sum(economy.markets[c].price_minor * DAILY_PER_RESIDENT[c] for c in essentials)
        rent_per_resident = economy.markets["housing"].price_minor / (
            30.0 * max(1.2, ctx.config.population.household_size_mean)
        )
        living_cost = basket_cost + rent_per_resident
        district_income = _district_income_table(agents, government)
        unrest_total = 0.0

        for cohort_id in sorted(agents.cohorts):
            cohort = agents.cohorts[cohort_id]
            if cohort.size <= 0 or not cohort.account_id:
                continue
            workers = int(cohort.size * cohort.employment_rate)
            daily_income = cohort.daily_income_minor
            if workers > 0 and daily_income > 0:
                cohort.average_income_minor = int(daily_income * 30.0 / workers)

            benefit = (
                int((cohort.size - workers) * government.welfare_per_day_minor * 0.6)
                if cohort.age_band != "0_17" else 0
            )
            if benefit > 0 and transfer(economy, treasury, cohort.account_id, benefit):
                government.spending_ytd_minor += benefit
                cohort.daily_income_minor += benefit
            else:
                benefit = 0
            income = daily_income + benefit

            # Rent for the dwellings this cohort occupies.
            cohort_households = cohort.size / max(1.2, ctx.config.population.household_size_mean)
            rent_today = int(economy.markets["housing"].price_minor * cohort_households / 30.0)
            spent_today = 0
            if rent_today > 0 and transfer(economy, cohort.account_id, economy.escrow_account_id, rent_today):
                spent_today += rent_today

            # Whatever the day's necessities left over is spent, not hoarded.
            discretionary = cohort.consumption_propensity * (0.5 + cohort.sentiment)
            spare = int(max(0, income - spent_today) * discretionary * (1.0 - SAVINGS_RATE))
            if spare > 0:
                for code, share in (("services", 0.42), ("consumer_goods", 0.26),
                                    ("healthcare", 0.13), ("education", 0.13), ("electronics", 0.06)):
                    price = economy.markets[code].price_minor
                    quantity = price_response(economy, code, (spare * share) / max(1, price))
                    if quantity <= 0.0:
                        continue
                    economy.markets[code].demand += quantity
                    bought = purchase(
                        economy,
                        buyer_account_id=cohort.account_id,
                        code=code,
                        quantity=quantity,
                        vat_rate=vat,
                        treasury_account_id=treasury,
                        allow_import=code == "consumer_goods",
                    )
                    government.revenue_ytd_minor += bought.tax_minor
            cohort.savings_minor = economy.balance(cohort.account_id)
            cohort.daily_income_minor = 0

            # How the cohort feels: living standards first, headlines second.
            per_resident_income = district_income.get(cohort.district_id, 0.0)
            band_tilt = {"low": 0.72, "mid": 1.0, "high": 1.6}[cohort.income_band]
            affordability = (per_resident_income * band_tilt) / max(1.0, living_cost)
            cohort.news_pressure = round(cohort.news_pressure * NEWS_DECAY_PER_DAY, 5)
            target_sentiment = min(
                0.95,
                max(
                    0.05,
                    0.15
                    + 0.55 * min(1.4, affordability)
                    + 0.2 * (cohort.employment_rate - 0.9)
                    + 0.25 * cohort.news_pressure,
                ),
            )
            cohort.sentiment = round(0.9 * cohort.sentiment + 0.1 * target_sentiment, 5)
            trust_target = max(0.02, min(0.98, target_sentiment * 0.7 + 0.3 + 0.3 * cohort.news_pressure))
            cohort.trust_government = round(
                min(0.98, max(0.02, 0.94 * cohort.trust_government + 0.06 * trust_target)), 5
            )
            unrest_target = (
                max(0.0, 0.45 - cohort.sentiment) * 0.8 + max(0.0, 0.6 - cohort.employment_rate) * 0.5
            )
            cohort.unrest = round(min(1.0, 0.88 * cohort.unrest + 0.12 * unrest_target), 5)
            unrest_total += cohort.unrest * cohort.size

            if cohort.unrest > 0.4 and rng.chance(cohort.unrest * 0.25):
                district = geography.districts.get(cohort.district_id)
                if district is not None:
                    district.unrest = round(min(1.0, district.unrest + 0.05), 4)
                government.protests_active += 1
                ctx.emit(
                    Topics.PERSON_PROTEST,
                    "protest",
                    actor=cohort.cohort_id,
                    location=cohort.district_id,
                    payload={
                        "participants": int(cohort.size * cohort.unrest * 0.3),
                        "grievance": "cost_of_living" if affordability < 0.9 else "unemployment",
                        "unrest": cohort.unrest,
                    },
                    inputs=ImportanceInputs(
                        people_affected=cohort.size * cohort.unrest * 0.3,
                        political_impact=0.6,
                        risk=0.4,
                    ),
                    visibility=Visibility.PUBLIC,
                )

        population_total = max(1, agents.total_population())
        government.unrest_index = round(unrest_total / population_total, 5)
        ctx.telemetry.gauge("unrest_index", government.unrest_index)
        ctx.telemetry.gauge("affordability", round(
            sum(district_income.values()) / max(1, len(district_income)) / max(1.0, living_cost), 4
        ))
        ctx.telemetry.gauge("cohort_sentiment", round(
            sum(c.sentiment * c.size for c in agents.cohorts.values()) / max(1, agents.cohort_population()), 4
        ))


def _district_income_table(agents: AgentsState, government: GovernmentState) -> dict[str, float]:
    """Daily income per resident, by district, counting wages, pensions and benefits."""

    income: dict[str, list[float]] = {}
    for cohort in agents.cohorts.values():
        workers = cohort.size * cohort.employment_rate
        wages = workers * cohort.average_income_minor / 30.0
        pensions = (cohort.size * 0.55 * cohort.average_income_minor / 30.0) if cohort.age_band == "65_plus" else 0.0
        benefits = (
            (cohort.size - workers) * government.welfare_per_day_minor * 0.6
            if cohort.age_band != "0_17" else 0.0
        )
        bucket = income.setdefault(cohort.district_id, [0.0, 0.0])
        bucket[0] += wages + pensions + benefits
        bucket[1] += cohort.size
    return {district: total / max(1.0, size) for district, (total, size) in income.items()}
