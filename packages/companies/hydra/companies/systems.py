"""Company systems: production, payroll and firm decisions.

This is where the causal chain of the demo scenario actually lives. Nothing here knows about
"a scenario": a firm looks at its own unit cost, margin, cash and order book, and decides.
When electricity gets expensive, energy-intensive firms see it first — in their books.
"""

from __future__ import annotations

from hydra.agents.model import AgentsState, Employment
from hydra.economy.clearing import purchase
from hydra.economy.model import EconomyState
from hydra.economy.money import transfer
from hydra.economy.pricing import unit_cost_minor
from hydra.economy.systems import post_opening
from hydra.events.importance import ImportanceInputs
from hydra.events.model import Topics
from hydra.geography.model import GeographyState
from hydra.government.model import GovernmentState
from hydra.kernel.clock import TICKS_PER_DAY
from hydra.kernel.systems import Phase, SystemSpec

from .model import CompaniesState, Company, Sector, Strategy

WORK_HOURS_PER_DAY = 7.0
DAYS_PER_MONTH = 30.0


class ProductionSystem:
    """Buy inputs, burn energy, use labour, make goods. Missing inputs cut output."""

    spec = SystemSpec(
        name="production",
        phase=Phase.PHYSICAL,
        cadence_ticks=6,
        priority=20,
        reads=("companies", "economy", "geography", "agents"),
        writes=("companies", "economy", "geography"),
        emits=(Topics.ECON_PRODUCTION, Topics.COMPANY_OUTPUT_CUT),
        description="BOM-driven production: inputs, energy and labour constrain real output.",
    )

    def __init__(self, cadence_ticks: int = 6) -> None:
        self.spec = ProductionSystem.spec.with_cadence(cadence_ticks)
        self._cycles_per_day = max(1.0, TICKS_PER_DAY / max(1, cadence_ticks))
        self._hours_per_worker = WORK_HOURS_PER_DAY / self._cycles_per_day

    def step(self, ctx) -> None:  # noqa: ANN001
        companies = ctx.state.domain(CompaniesState)
        economy = ctx.state.domain(EconomyState)
        geography = ctx.state.domain(GeographyState)
        government = ctx.state.domain(GovernmentState)
        city = geography.city()

        power_reliability = min(
            1.0,
            city.infrastructure.power_output_mw / max(1e-6, city.infrastructure.power_demand_mw),
        )

        for company_id in sorted(companies.companies):
            company = companies.companies[company_id]
            if company.bankrupt:
                continue
            recipe = economy.recipes.get(company.recipe_code)
            if recipe is None:
                continue
            if company.product_code == "electricity":
                # Generators are dispatched by the grid; production here would double-count
                # both the kilowatt-hours and the money.
                continue

            target = company.capacity_units * company.utilisation / self._cycles_per_day
            if target <= 0.0:
                continue

            # Labour ceiling: people are a hard constraint, not a cost multiplier.
            if recipe.labour_hours > 0.0:
                labour_units = company.headcount() * self._hours_per_worker / recipe.labour_hours
                target = min(target, labour_units)

            # Energy: bought at market price, scaled by how energy-hungry the sector is.
            energy_needed = recipe.energy_kwh * target * company.energy_intensity / max(0.4, company.technology + 0.6)
            spent = 0
            if energy_needed > 0.0:
                economy.markets["electricity"].demand += energy_needed
                bought = purchase(
                    economy,
                    buyer_account_id=company.account_id,
                    code="electricity",
                    quantity=energy_needed,
                    allow_import=False,
                )
                spent += bought.spent_minor
                energy_ratio = bought.filled / max(1e-9, energy_needed)
                target *= max(0.05, min(1.0, energy_ratio * power_reliability))

            # Material inputs.
            for input_code in sorted(recipe.inputs):
                qty_per_unit = recipe.inputs[input_code]
                needed = qty_per_unit * target
                stock = company.input_stock.get(input_code, 0.0)
                deficit = needed - stock
                if deficit > 0.0:
                    economy.markets[input_code].demand += deficit
                    bought = purchase(
                        economy,
                        buyer_account_id=company.account_id,
                        code=input_code,
                        quantity=deficit * 1.15,          # firms hold a small buffer
                    )
                    spent += bought.spent_minor
                    stock += bought.filled
                    company.input_stock[input_code] = stock
                if needed > 0.0:
                    target = min(target, stock / qty_per_unit)

            output = max(0.0, round(target, 4))
            for input_code in sorted(recipe.inputs):
                used = recipe.inputs[input_code] * output
                company.input_stock[input_code] = max(0.0, company.input_stock.get(input_code, 0.0) - used)

            previous = company.output_units
            company.output_units = output
            company.costs_minor += spent

            produced = output * recipe.output_qty
            company.inventory[company.product_code] = company.inventory.get(company.product_code, 0.0) + produced
            market = economy.markets[company.product_code]
            if company.product_code == "housing":
                # Builders make dwellings; the housing system turns finished units into
                # capacity and prices the rental market against the household count.
                continue
            market.supply += produced
            market.inventory += produced
            company.supplied_window += produced

            if previous > 0.0 and output < previous * 0.8:
                ctx.emit(
                    Topics.COMPANY_OUTPUT_CUT,
                    "output_constrained",
                    actor=company.company_id,
                    location=company.district_id,
                    payload={
                        "output": round(output, 3),
                        "previous": round(previous, 3),
                        "product": company.product_code,
                    },
                    inputs=ImportanceInputs(
                        people_affected=company.headcount(),
                        economic_impact=(previous - output) * market.price_minor,
                        political_impact=0.12,
                        risk=0.1,
                    ),
                )

        ctx.telemetry.gauge(
            "production_units", float(round(sum(c.output_units for c in companies.active()), 2))
        )
        _ = government


class PayrollSystem:
    """Wages and income tax, every simulated day."""

    spec = SystemSpec(
        name="payroll",
        phase=Phase.INSTITUTIONS,
        cadence_ticks=TICKS_PER_DAY,
        priority=40,     # after the daily books are closed, so wages land in one day only
        reads=("companies", "agents", "economy", "government"),
        writes=("companies", "agents", "economy", "government"),
        emits=(),
        description="Pays wages to individuals and cohort staff; collects income tax.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        companies = ctx.state.domain(CompaniesState)
        agents = ctx.state.domain(AgentsState)
        economy = ctx.state.domain(EconomyState)
        government = ctx.state.domain(GovernmentState)
        treasury = government.treasury_account_id
        tax_rate = government.income_tax_rate
        paid_total = 0
        tax_total = 0
        for cohort in agents.cohorts.values():
            cohort.daily_income_minor = 0

        for company_id in sorted(companies.companies):
            company = companies.companies[company_id]
            if company.bankrupt:
                continue
            wage_bill = 0
            for person_id in list(company.employee_ids):
                person = agents.people.get(person_id)
                if person is None or not person.alive:
                    company.employee_ids.remove(person_id)
                    continue
                daily = int(person.wage_minor / DAYS_PER_MONTH)
                if daily <= 0:
                    continue
                net = daily - int(daily * tax_rate)
                if transfer(economy, company.account_id, person.account_id, net):
                    transfer(economy, company.account_id, treasury, daily - net)
                    wage_bill += daily
                    tax_total += daily - net
                else:
                    company.months_of_loss += 1
                    break
            for cohort_id, headcount in sorted(company.cohort_employees.items()):
                cohort = agents.cohorts.get(cohort_id)
                if cohort is None or headcount <= 0 or not cohort.account_id:
                    continue
                daily = int(company.average_wage_minor / DAYS_PER_MONTH) * headcount
                if daily <= 0:
                    continue
                net = daily - int(daily * tax_rate)
                if transfer(economy, company.account_id, cohort.account_id, net):
                    transfer(economy, company.account_id, treasury, daily - net)
                    cohort.savings_minor = economy.balance(cohort.account_id)
                    cohort.daily_income_minor += net
                    wage_bill += daily
                    tax_total += daily - net
            company.costs_minor += wage_bill
            paid_total += wage_bill

        # People the world simulates individually are entitled to the same benefit the
        # cohorts receive; without it a layoff would erase someone's demand entirely.
        benefits = 0
        for person in agents.people.values():
            if not person.alive or person.age_years < 18:
                continue
            if person.employment not in (Employment.UNEMPLOYED, Employment.RETIRED):
                continue
            amount = government.welfare_per_day_minor if person.employment is Employment.UNEMPLOYED else int(
                government.welfare_per_day_minor * 1.4
            )
            if transfer(economy, treasury, person.account_id, amount):
                benefits += amount
        government.spending_ytd_minor += benefits

        government.revenue_ytd_minor += tax_total
        ctx.telemetry.gauge("benefits_paid_minor", float(benefits))
        ctx.telemetry.gauge("wages_paid_minor", float(paid_total))
        ctx.telemetry.gauge("income_tax_minor", float(tax_total))


class CompanyDecisionSystem:
    """The firm's daily board meeting: price, output, hiring, borrowing, survival."""

    spec = SystemSpec(
        name="company_decisions",
        phase=Phase.INSTITUTIONS,
        cadence_ticks=TICKS_PER_DAY,
        priority=30,
        reads=("companies", "economy", "agents", "government"),
        writes=("companies", "economy", "agents"),
        emits=(
            Topics.COMPANY_PRICE,
            Topics.COMPANY_LAYOFF,
            Topics.COMPANY_HIRE,
            Topics.COMPANY_INVEST,
            Topics.COMPANY_BANKRUPT,
            Topics.PERSON_JOB_LOST,
        ),
        description="Margin, cash and demand drive pricing, output, hiring, layoffs, bankruptcy.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        companies = ctx.state.domain(CompaniesState)
        economy = ctx.state.domain(EconomyState)
        agents = ctx.state.domain(AgentsState)
        config = ctx.config.economy
        rng = ctx.rng("company_decisions")

        for company_id in sorted(companies.companies):
            company = companies.companies[company_id]
            if company.bankrupt:
                continue
            market = economy.markets[company.product_code]
            company.unit_cost_minor = unit_cost_minor(economy, company.recipe_code)
            wage_bill = self._daily_wage_bill(company, agents)
            cash = economy.balance(company.account_id)
            profit = company.revenue_minor - company.costs_minor
            company.profit_history.append(profit)
            del company.profit_history[:-30]

            margin = (market.price_minor - company.unit_cost_minor) / max(1, market.price_minor)
            price_target = int(company.unit_cost_minor * (1.0 + config.target_margin))
            new_price = int(0.6 * market.price_minor + 0.4 * price_target)
            if abs(new_price - company.price_minor) > company.price_minor * 0.01:
                company.price_minor = new_price

            if profit < 0:
                company.months_of_loss += 1
            else:
                company.months_of_loss = max(0, company.months_of_loss - 1)

            recipe = economy.recipes.get(company.recipe_code)
            # Staffing follows installed capacity, not this week's output: a firm that
            # throttles production for a fortnight does not fire its workforce over it.
            labour_hours = company.capacity_units * 0.9 * (recipe.labour_hours if recipe else 0.02)
            company.headcount_target = max(1, int(round(labour_hours / WORK_HOURS_PER_DAY)))

            company.strategy = self._choose_strategy(company, margin, cash, wage_bill, config)
            company.last_decision = company.strategy.value

            # Overstaffing is its own reason to shed jobs, independent of the margin.
            if company.headcount() > company.headcount_target * 1.25 and company.months_of_loss >= 3:
                self._lay_off(ctx, company, agents, companies, rng)

            if company.strategy is Strategy.COST_CUT:
                self._cut_output(ctx, company, market)
                if company.months_of_loss >= 3 and cash < wage_bill * config.layoff_cash_months * DAYS_PER_MONTH:
                    self._lay_off(ctx, company, agents, companies, rng)
            elif company.strategy is Strategy.SURVIVE:
                if company.months_of_loss >= 5:
                    self._borrow(ctx, company, economy, wage_bill)
            elif company.strategy in (Strategy.GROW, Strategy.INVEST):
                self._expand(ctx, company, companies, margin, rng)

            if cash <= 0 and company.debt_minor > 0 and company.months_of_loss >= 8:
                self._bankrupt(ctx, company, companies, agents)

            company.revenue_minor = 0
            company.costs_minor = 0

        ctx.telemetry.gauge("companies_active", float(len(companies.active())))
        ctx.telemetry.gauge("layoffs_total", float(companies.total_layoffs))

    # -- decision helpers ---------------------------------------------------------
    @staticmethod
    def _daily_wage_bill(company: Company, agents: AgentsState) -> int:
        total = sum(
            int(agents.people[p].wage_minor / DAYS_PER_MONTH)
            for p in company.employee_ids
            if p in agents.people
        )
        total += sum(
            int(company.average_wage_minor / DAYS_PER_MONTH) * headcount
            for headcount in company.cohort_employees.values()
        )
        return max(1, total)

    @staticmethod
    def _choose_strategy(company: Company, margin: float, cash: int, wage_bill: int, config) -> Strategy:  # noqa: ANN001
        runway_days = cash / max(1, wage_bill)
        if margin < 0.0 or runway_days < 20:
            return Strategy.COST_CUT
        if margin < 0.05:
            return Strategy.SURVIVE
        if margin > config.hiring_margin_threshold and company.utilisation > 0.86:
            return Strategy.GROW
        if margin > config.hiring_margin_threshold * 1.6:
            return Strategy.INVEST
        return Strategy.MILK

    def _cut_output(self, ctx, company: Company, market) -> None:  # noqa: ANN001
        previous = company.utilisation
        company.utilisation = round(max(0.25, company.utilisation * 0.9), 4)
        if company.utilisation < previous - 0.02:
            ctx.emit(
                Topics.COMPANY_OUTPUT_CUT,
                "output_cut",
                actor=company.company_id,
                location=company.district_id,
                payload={
                    "utilisation": company.utilisation,
                    "previous": previous,
                    "unit_cost_minor": company.unit_cost_minor,
                    "product": company.product_code,
                },
                inputs=ImportanceInputs(
                    people_affected=company.headcount(),
                    economic_impact=(previous - company.utilisation) * company.capacity_units * market.price_minor,
                    political_impact=0.15,
                    risk=0.12,
                ),
            )

    def _lay_off(self, ctx, company: Company, agents: AgentsState, companies: CompaniesState, rng) -> None:  # noqa: ANN001
        headcount = company.headcount()
        if headcount <= 1:
            return
        share = 0.12 if company.months_of_loss < 6 else 0.2
        count = max(1, int(headcount * share))
        released = 0

        individuals = [p for p in company.employee_ids if p in agents.people]
        for person_id in rng.sample(individuals, min(len(individuals), count)):
            person = agents.people[person_id]
            company.employee_ids.remove(person_id)
            person.employment = Employment.UNEMPLOYED
            person.employer_id = ""
            person.work_building_id = ""
            person.stress = round(min(1.0, person.stress + 0.25), 4)
            person.mood = round(max(0.0, person.mood - 0.2), 4)
            released += 1
            ctx.emit(
                Topics.PERSON_JOB_LOST,
                "lost_job",
                actor=person_id,
                target=company.company_id,
                location=company.district_id,
                payload={"company": company.name},
                inputs=ImportanceInputs(
                    people_affected=1,
                    economic_impact=person.wage_minor,
                    political_impact=0.08,
                    risk=0.2,
                    proximity=0.6,
                ),
            )

        remaining = count - released
        for cohort_id in sorted(company.cohort_employees):
            if remaining <= 0:
                break
            headcount_here = company.cohort_employees[cohort_id]
            take = min(headcount_here, remaining)
            company.cohort_employees[cohort_id] = headcount_here - take
            cohort = agents.cohorts.get(cohort_id)
            if cohort is not None and cohort.size > 0:
                cohort.employment_rate = round(max(0.0, cohort.employment_rate - take / cohort.size), 6)
                cohort.sentiment = round(max(0.0, cohort.sentiment - 0.03), 4)
            remaining -= take
            released += take

        if released <= 0:
            return
        company.layoffs_total += released
        companies.total_layoffs += released
        ctx.emit(
            Topics.COMPANY_LAYOFF,
            "laid_off_workers",
            actor=company.company_id,
            location=company.district_id,
            payload={
                "count": released,
                "headcount_left": company.headcount(),
                "unit_cost_minor": company.unit_cost_minor,
                "sector": company.sector.value,
                "company_name": company.name,
            },
            inputs=ImportanceInputs(
                people_affected=released * 2.4,        # households, not just workers
                economic_impact=released * company.average_wage_minor,
                political_impact=0.45,
                risk=0.35,
            ),
        )

    def _expand(self, ctx, company: Company, companies: CompaniesState, margin: float, rng) -> None:  # noqa: ANN001
        company.utilisation = round(min(0.98, company.utilisation * 1.03), 4)
        if company.strategy is Strategy.INVEST and company.utilisation > 0.94:
            # Running flat out at a fat margin is the signal to build, not just to hire.
            economy = ctx.state.domain(EconomyState)
            from hydra.economy.clearing import purchase

            spend = int(economy.balance(company.account_id) * 0.05)
            if spend > 0:
                units = spend / max(1, economy.markets["materials"].price_minor)
                economy.markets["materials"].demand += units
                bought = purchase(
                    economy, buyer_account_id=company.account_id, code="materials", quantity=units
                )
                if bought.filled > 0:
                    company.capacity_units = round(company.capacity_units * (1.0 + 0.02 * margin * 5), 3)
                    company.costs_minor += bought.spent_minor
                    ctx.emit(
                        Topics.COMPANY_INVEST,
                        "invested",
                        actor=company.company_id,
                        location=company.district_id,
                        payload={"spend_minor": bought.spent_minor, "capacity": company.capacity_units},
                        importance=0.12,
                    )
        if not rng.chance(0.35):
            return
        positions = max(1, int(company.headcount() * 0.05))
        post_opening(
            companies,
            company,
            tick=ctx.tick,
            role=f"{company.sector.value} worker",
            wage_minor=company.average_wage_minor,
            skill=_sector_skill(company.sector),
            skill_required=round(0.25 + 0.4 * company.technology, 3),
            positions=positions,
        )
        ctx.emit(
            Topics.COMPANY_HIRE,
            "posted_jobs",
            actor=company.company_id,
            location=company.district_id,
            payload={"positions": positions, "wage_minor": company.average_wage_minor},
            importance=0.12,
        )

    def _borrow(self, ctx, company: Company, economy: EconomyState, wage_bill: int) -> None:  # noqa: ANN001
        banks = sorted(economy.banks.values(), key=lambda b: b.bank_id)
        if not banks:
            return
        bank = max(banks, key=lambda b: b.risk_appetite * (b.capital_minor - b.npl_minor))
        amount = wage_bill * 45
        if amount <= 0 or economy.balance(bank.account_id) < amount:
            return
        economy.next_loan_index += 1
        loan_id = f"loan_{economy.next_loan_index:06d}"
        rate = economy.policy_rate + bank.spread + 0.02 * company.months_of_loss / 10.0
        from hydra.economy.model import Loan

        economy.loans[loan_id] = Loan(
            loan_id=loan_id,
            borrower_id=company.company_id,
            bank_id=bank.bank_id,
            principal_minor=amount,
            outstanding_minor=amount,
            annual_rate=round(rate, 5),
            issued_tick=ctx.tick,
            term_days=720,
            next_payment_tick=ctx.tick + TICKS_PER_DAY * 30,
            payment_minor=int(amount / 24),
        )
        bank.loan_ids.append(loan_id)
        transfer(economy, bank.account_id, company.account_id, amount)
        company.debt_minor += amount
        ctx.emit(
            Topics.BANK_LOAN,
            "loan_issued",
            actor=bank.bank_id,
            target=company.company_id,
            payload={"amount_minor": amount, "rate": round(rate, 5)},
            importance=0.15,
        )

    def _bankrupt(self, ctx, company: Company, companies: CompaniesState, agents: AgentsState) -> None:  # noqa: ANN001
        company.bankrupt = True
        companies.bankruptcies += 1
        released = 0
        for person_id in list(company.employee_ids):
            person = agents.people.get(person_id)
            if person is None:
                continue
            person.employment = Employment.UNEMPLOYED
            person.employer_id = ""
            person.stress = round(min(1.0, person.stress + 0.3), 4)
            released += 1
        released += sum(company.cohort_employees.values())
        for cohort_id, headcount in company.cohort_employees.items():
            cohort = agents.cohorts.get(cohort_id)
            if cohort is not None and cohort.size:
                cohort.employment_rate = round(max(0.0, cohort.employment_rate - headcount / cohort.size), 6)
        company.employee_ids.clear()
        company.cohort_employees.clear()
        companies.total_layoffs += released
        ctx.emit(
            Topics.COMPANY_BANKRUPT,
            "went_bankrupt",
            actor=company.company_id,
            location=company.district_id,
            payload={"jobs_lost": released, "sector": company.sector.value, "company_name": company.name},
            inputs=ImportanceInputs(
                people_affected=released * 2.4,
                economic_impact=company.debt_minor,
                political_impact=0.4,
                risk=0.4,
            ),
        )


def _sector_skill(sector: Sector) -> str:
    if sector in (Sector.TECH, Sector.ELECTRONICS, Sector.FINANCE, Sector.EDUCATION, Sector.HEALTHCARE, Sector.MEDIA):
        return "analytical"
    if sector in (Sector.SERVICES, Sector.RETAIL):
        return "social"
    if sector in (Sector.ENERGY, Sector.WATER, Sector.MANUFACTURING):
        return "technical"
    return "manual"
