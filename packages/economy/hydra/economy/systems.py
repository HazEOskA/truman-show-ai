"""Economy systems: market clearing, banking and the labour market."""

from __future__ import annotations

from hydra.agents.model import AgentsState, Employment
from hydra.companies.model import CompaniesState, JobOpening
from hydra.events.importance import ImportanceInputs
from hydra.events.model import Topics
from hydra.kernel.clock import TICKS_PER_DAY, TICKS_PER_MONTH
from hydra.kernel.systems import Phase, SystemSpec
from hydra.population.model import PopulationState

from hydra.government.model import GovernmentState, PolicyKind

from .clearing import settle_producers
from .model import EconomyState
from .money import transfer
from .pricing import consumer_price_index, next_price_minor, unit_cost_minor, update_expectation

PRICE_EVENT_THRESHOLD = 0.02
EXPORT_COVER_DAYS = 8.0
EXPORT_DISCOUNT = 0.95
SHORTAGE_RATIO = 0.05


class MarketSystem:
    """Turns the last cycle's supply and demand into new prices, then pays producers."""

    spec = SystemSpec(
        name="markets",
        phase=Phase.MARKETS,
        cadence_ticks=6,
        priority=10,
        reads=("economy", "companies", "geography", "government"),
        writes=("economy", "companies"),
        emits=(Topics.MARKET_PRICE_MOVE, Topics.MARKET_SHORTAGE, Topics.ECON_INFLATION),
        description="Price formation from supply, demand, inventory, cost and expectations.",
    )

    def __init__(self, cadence_ticks: int = 6) -> None:
        self.spec = MarketSystem.spec.with_cadence(cadence_ticks)

    def step(self, ctx) -> None:  # noqa: ANN001
        economy = ctx.state.domain(EconomyState)
        companies = ctx.state.domain(CompaniesState)
        config = ctx.config.economy

        settle_producers(economy, companies)

        cycle_value = 0
        for code in sorted(economy.markets):
            market = economy.markets[code]
            market.unit_cost_minor = unit_cost_minor(economy, code)
            market.previous_price_minor = market.price_minor
            new_price = next_price_minor(
                economy,
                code,
                target_margin=config.target_margin,
                change_cap=config.price_change_cap,
                drift=config.base_price_drift,
                cycles_per_day=TICKS_PER_DAY / max(1, self.spec.cadence_ticks),
            )
            new_price = self._apply_policies(ctx, code, new_price)
            change = (new_price - market.price_minor) / max(1, market.price_minor)
            market.price_minor = new_price
            market.record_price()
            update_expectation(economy, code)
            cycle_value += int(market.transacted * market.price_minor)

            if abs(change) >= PRICE_EVENT_THRESHOLD:
                ctx.emit(
                    Topics.MARKET_PRICE_MOVE,
                    "price_moved",
                    target=code,
                    payload={
                        "code": code,
                        "price_minor": new_price,
                        "change_pct": round(change * 100.0, 3),
                        "unit_cost_minor": market.unit_cost_minor,
                        "demand": round(market.demand, 2),
                        "supply": round(market.supply, 2),
                    },
                    inputs=ImportanceInputs(
                        people_affected=self._affected(ctx, code),
                        economic_impact=abs(change) * max(1, market.price_minor) * max(1.0, market.demand),
                        political_impact=0.35 if economy.goods[code].essential else 0.1,
                        risk=0.25 if economy.goods[code].essential and change > 0 else 0.05,
                    ),
                )

            if market.demand > 0 and market.unmet_demand / max(1e-6, market.demand) > SHORTAGE_RATIO:
                market.shortage_ticks += 1
                if market.shortage_ticks % 3 == 1:
                    ctx.emit(
                        Topics.MARKET_SHORTAGE,
                        "shortage",
                        target=code,
                        payload={
                            "code": code,
                            "unmet": round(market.unmet_demand, 2),
                            "demand": round(market.demand, 2),
                        },
                        inputs=ImportanceInputs(
                            people_affected=self._affected(ctx, code),
                            economic_impact=market.unmet_demand * market.price_minor,
                            political_impact=0.5 if economy.goods[code].essential else 0.2,
                            risk=0.45 if economy.goods[code].essential else 0.15,
                        ),
                    )
            else:
                market.shortage_ticks = 0

            if ctx.now.hour == 4 and economy.goods[code].perishable_daily > 0.0:
                # Yesterday's unsold seats and appointments are gone.
                market.inventory = round(market.inventory * (1.0 - economy.goods[code].perishable_daily), 4)
            self._export_surplus(economy, code, market)
            market.last_demand = market.demand
            market.demand_ema = round(market.demand_ema + (market.demand - market.demand_ema) / 24.0, 4)

        economy.volume_minor += cycle_value
        economy.cpi = consumer_price_index(economy)
        economy.cpi_history.append(economy.cpi)
        del economy.cpi_history[:-8640]

        # Annualised from a month of CPI, not from one cycle: hourly noise is not inflation.
        cycles_per_month = max(1, int(TICKS_PER_MONTH / max(1, self.spec.cadence_ticks)))
        if len(economy.cpi_history) > cycles_per_month:
            month_ago = economy.cpi_history[-cycles_per_month - 1]
            economy.inflation_annual = round(
                max(-0.95, min(5.0, (economy.cpi / max(1e-6, month_ago)) ** 12 - 1.0)), 6
            )
        ctx.telemetry.gauge("cpi", economy.cpi)
        ctx.telemetry.gauge("inflation_annual", economy.inflation_annual)
        ctx.telemetry.gauge("energy_price", float(economy.markets["electricity"].price_minor))

    @staticmethod
    def _export_surplus(economy: EconomyState, code: str, market) -> None:  # noqa: ANN001
        """Stock nobody in Hydra wants is sold out of the city.

        Without an export leg the city runs a permanent trade deficit against its own
        warehouses: imports drain money out, surplus stock traps value in, and producers
        slowly starve between the two.
        """

        good = economy.goods[code]
        if not good.storable or market.demand <= 0.0:
            return
        cover_days = market.inventory / max(1e-6, market.demand * 24.0)
        if cover_days <= EXPORT_COVER_DAYS:
            return
        surplus = min(market.inventory * 0.25, market.inventory - EXPORT_COVER_DAYS * market.demand * 24.0)
        if surplus <= 0.0:
            return
        value = int(surplus * market.price_minor * EXPORT_DISCOUNT)
        if value <= 0:
            return
        from .money import transfer

        if transfer(economy, economy.external_account_id, economy.escrow_account_id, value):
            market.inventory = max(0.0, market.inventory - surplus)
            economy.exports_minor += value

    @staticmethod
    def _apply_policies(ctx, code: str, price: int) -> int:  # noqa: ANN001
        """Government intervention lands here, and only here."""

        government = ctx.state.domain(GovernmentState)
        for policy in government.active_policies():
            if policy.target != code:
                continue
            if policy.kind is PolicyKind.PRICE_CAP and policy.value > 0:
                price = min(price, int(policy.value))
            elif policy.kind is PolicyKind.ENERGY_SUBSIDY:
                price = max(1, int(price * (1.0 - policy.value)))
        return price

    @staticmethod
    def _affected(ctx, code: str) -> float:  # noqa: ANN001
        agents = ctx.state.domain(AgentsState)
        good = ctx.state.domain(EconomyState).goods[code]
        return agents.total_population() * (1.0 if good.essential else 0.25)


class BankingSystem:
    """Loan servicing, defaults and deposit interest — the slow financial cycle."""

    spec = SystemSpec(
        name="banking",
        phase=Phase.MARKETS,
        cadence_ticks=TICKS_PER_DAY,
        priority=40,
        reads=("economy", "companies", "agents"),
        writes=("economy", "companies"),
        emits=(Topics.BANK_LOAN, Topics.BANK_DEFAULT),
        description="Services loans, records defaults, keeps bank balance sheets honest.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        economy = ctx.state.domain(EconomyState)
        companies = ctx.state.domain(CompaniesState)
        tick = ctx.tick

        for loan_id in sorted(economy.loans):
            loan = economy.loans[loan_id]
            if loan.defaulted or loan.outstanding_minor <= 0 or loan.next_payment_tick > tick:
                continue
            bank = economy.banks.get(loan.bank_id)
            if bank is None:
                continue
            interest = int(loan.outstanding_minor * loan.annual_rate / 360.0)
            payment = min(loan.outstanding_minor + interest, max(loan.payment_minor, interest))
            borrower_account = self._account_for(economy, companies, loan.borrower_id)
            if borrower_account and transfer(economy, borrower_account, bank.account_id, payment):
                loan.outstanding_minor = max(0, loan.outstanding_minor + interest - payment)
                loan.missed_payments = 0
            else:
                loan.missed_payments += 1
                if loan.missed_payments >= 3:
                    loan.defaulted = True
                    bank.npl_minor += loan.outstanding_minor
                    company = companies.companies.get(loan.borrower_id)
                    ctx.emit(
                        Topics.BANK_DEFAULT,
                        "loan_default",
                        actor=loan.borrower_id,
                        target=loan.bank_id,
                        payload={"outstanding_minor": loan.outstanding_minor},
                        inputs=ImportanceInputs(
                            people_affected=company.headcount() if company else 1,
                            economic_impact=loan.outstanding_minor,
                            political_impact=0.15,
                            risk=0.3,
                        ),
                    )
            loan.next_payment_tick = tick + TICKS_PER_DAY * 30
            if company := companies.companies.get(loan.borrower_id):
                company.debt_minor = sum(
                    l.outstanding_minor for l in economy.loans.values()
                    if l.borrower_id == company.company_id and not l.defaulted
                )

        for bank in economy.banks.values():
            bank.loans_minor = sum(
                l.outstanding_minor for l in economy.loans.values()
                if l.bank_id == bank.bank_id and not l.defaulted
            )
        ctx.telemetry.gauge("loans_outstanding", float(sum(b.loans_minor for b in economy.banks.values())))

    @staticmethod
    def _account_for(economy: EconomyState, companies: CompaniesState, owner_id: str) -> str:
        company = companies.companies.get(owner_id)
        if company is not None:
            return company.account_id
        for account in economy.accounts.values():
            if account.owner_id == owner_id:
                return account.account_id
        return ""


class LabourMarketSystem:
    """Matches openings to job seekers once a day and recomputes unemployment."""

    spec = SystemSpec(
        name="labour_market",
        phase=Phase.MARKETS,
        cadence_ticks=TICKS_PER_DAY,
        priority=30,
        reads=("companies", "agents", "population", "economy"),
        writes=("companies", "agents", "population", "economy"),
        emits=(Topics.PERSON_HIRED, Topics.COMPANY_HIRE),
        description="Job matching for individuals and cohorts; unemployment and wage index.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        companies = ctx.state.domain(CompaniesState)
        agents = ctx.state.domain(AgentsState)
        population = ctx.state.domain(PopulationState)
        economy = ctx.state.domain(EconomyState)
        rng = ctx.rng("labour_market")

        seekers = [
            p for p in agents.people.values()
            if p.alive and p.employment is Employment.UNEMPLOYED and 18 <= p.age_years <= 66
        ]
        seekers.sort(key=lambda p: p.person_id)

        openings = [o for o in companies.openings.values() if o.positions > o.filled]
        openings.sort(key=lambda o: (-o.wage_minor, o.opening_id))

        hires = 0
        for opening in openings:
            company = companies.companies.get(opening.company_id)
            if company is None or company.bankrupt:
                continue
            while opening.filled < opening.positions and seekers:
                # Local candidates first: distance is a real friction in a city.
                candidate = None
                for index, person in enumerate(seekers):
                    if person.district_id == company.district_id or rng.chance(0.35):
                        candidate = seekers.pop(index)
                        break
                if candidate is None:
                    candidate = seekers.pop(0)
                skill = candidate.skills.get(opening.skill, 0.4)
                if skill + 0.15 < opening.skill_required and rng.chance(0.7):
                    continue
                candidate.employer_id = company.company_id
                candidate.employment = Employment.EMPLOYED
                candidate.work_building_id = company.building_id
                candidate.wage_minor = int(opening.wage_minor * (0.85 + 0.3 * skill))
                company.employee_ids.append(candidate.person_id)
                company.hires_total += 1
                opening.filled += 1
                hires += 1
                companies.total_hires += 1
                ctx.emit(
                    Topics.PERSON_HIRED,
                    "hired",
                    actor=candidate.person_id,
                    target=company.company_id,
                    location=company.district_id,
                    payload={"wage_minor": candidate.wage_minor, "role": opening.role},
                    importance=0.12,
                )
            if opening.filled >= opening.positions:
                companies.openings.pop(opening.opening_id, None)

        # Cohort-level hiring absorbs the rest of the demand statistically.
        for opening_id in sorted(companies.openings):
            opening = companies.openings[opening_id]
            company = companies.companies.get(opening.company_id)
            if company is None or company.bankrupt:
                companies.openings.pop(opening_id, None)
                continue
            remaining = opening.positions - opening.filled
            if remaining <= 0:
                continue
            pool = [
                c for c in agents.cohorts.values()
                if c.district_id == company.district_id and c.employment_rate < 0.985 and c.age_band not in ("0_17", "65_plus")
            ] or [c for c in agents.cohorts.values() if c.employment_rate < 0.985 and c.age_band not in ("0_17", "65_plus")]
            if not pool:
                continue
            cohort = rng.choice(sorted(pool, key=lambda c: c.cohort_id))
            unemployed = int(cohort.size * (1.0 - cohort.employment_rate))
            taken = min(remaining, max(0, unemployed))
            if taken <= 0:
                continue
            cohort.employment_rate = round(min(0.99, cohort.employment_rate + taken / max(1, cohort.size)), 6)
            company.cohort_employees[cohort.cohort_id] = company.cohort_employees.get(cohort.cohort_id, 0) + taken
            company.hires_total += taken
            opening.filled += taken
            hires += taken
            if opening.filled >= opening.positions:
                companies.openings.pop(opening_id, None)

        employed_individuals = sum(
            1 for p in agents.people.values()
            if p.alive and p.employment in (Employment.EMPLOYED, Employment.PUBLIC, Employment.SELF_EMPLOYED)
        )
        active_individuals = sum(
            1 for p in agents.people.values()
            if p.alive and 18 <= p.age_years <= 66 and p.employment is not Employment.STUDENT
        )
        cohort_labour = sum(c.size for c in agents.cohorts.values() if c.age_band not in ("0_17", "65_plus"))
        cohort_employed = sum(
            int(c.size * c.employment_rate) for c in agents.cohorts.values() if c.age_band not in ("0_17", "65_plus")
        )
        cohort_employed += sum(ctx.state.domain(GovernmentState).public_jobs.values())
        labour_force = max(1, active_individuals + cohort_labour)
        unemployment = 1.0 - (employed_individuals + cohort_employed) / labour_force
        economy.unemployment_rate = round(max(0.0, min(1.0, unemployment)), 6)
        population.unemployment_rate = economy.unemployment_rate
        companies.total_employment = sum(c.headcount() for c in companies.active())

        # Wage index follows the labour market with a lag, and feeds back into unit costs.
        pressure = (0.06 - economy.unemployment_rate) * 0.02
        economy.wage_index = round(max(0.5, min(3.0, economy.wage_index * (1.0 + pressure))), 6)
        ctx.telemetry.gauge("unemployment", economy.unemployment_rate)
        ctx.telemetry.gauge("hires", float(hires))
        ctx.telemetry.gauge("openings", float(len(companies.openings)))


class MarketCloseSystem:
    """Closes the trading window after everyone has traded in it.

    The window a price is computed from is "everything traded since the last pricing pass".
    Clearing those counters is therefore the very next thing that happens after a price is
    set — never in the middle of a tick, where it would throw away supply that had just been
    generated but not yet bought, and never at the end of one, where it would throw away the
    demand the pricing pass had not read yet.
    """

    spec = SystemSpec(
        name="market_close",
        phase=Phase.MARKETS,
        cadence_ticks=6,
        priority=20,          # immediately after pricing, before anyone trades again
        reads=("economy",),
        writes=("economy",),
        description="Ends the market cycle: clears per-cycle supply, demand and turnover.",
    )

    def __init__(self, cadence_ticks: int = 6) -> None:
        self.spec = MarketCloseSystem.spec.with_cadence(cadence_ticks)

    def step(self, ctx) -> None:  # noqa: ANN001
        economy = ctx.state.domain(EconomyState)
        for market in economy.markets.values():
            market.supply = 0.0
            market.demand = 0.0
            market.transacted = 0.0
            market.unmet_demand = 0.0


def post_opening(
    companies: CompaniesState,
    company,
    *,
    tick: int,
    role: str,
    wage_minor: int,
    skill: str,
    skill_required: float,
    positions: int,
) -> JobOpening:
    companies.next_opening_index += 1
    opening = JobOpening(
        opening_id=f"opening_{companies.next_opening_index:06d}",
        company_id=company.company_id,
        role=role,
        wage_minor=wage_minor,
        skill=skill,
        skill_required=skill_required,
        positions=positions,
        posted_tick=tick,
    )
    companies.openings[opening.opening_id] = opening
    return opening
