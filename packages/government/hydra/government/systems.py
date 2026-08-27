"""Government system: policy as a consequence, not a script.

Every simulated day the city government reads the same numbers an operator sees — prices,
unemployment, unrest, approval, the treasury — and acts within its ideology and its budget.
The mayor cannot conjure money; a subsidy is paid out of the treasury and shows up as debt.
"""

from __future__ import annotations

from hydra.agents.model import AgentsState
from hydra.economy.model import EconomyState
from hydra.economy.money import transfer
from hydra.events.importance import ImportanceInputs
from hydra.events.model import Topics
from hydra.geography.model import GeographyState
from hydra.kernel.clock import TICKS_PER_DAY, TICKS_PER_YEAR
from hydra.kernel.systems import Phase, SystemSpec

from .model import Election, GovernmentState, Policy, PolicyKind

ELECTION_PERIOD_TICKS = TICKS_PER_YEAR * 4
POLICY_WARMUP_TICKS = TICKS_PER_DAY * 10     # a new world's opening price drift is not a crisis
ENERGY_TREND_TRIGGER = 0.25
# A doubling of the energy price is a political fact on its own: a mayor does not wait for
# the streets to fill up before responding to it.
ENERGY_SPIKE_TRIGGER = 0.6
FOOD_TREND_TRIGGER = 0.22


class GovernmentSystem:
    spec = SystemSpec(
        name="government",
        phase=Phase.INSTITUTIONS,
        cadence_ticks=TICKS_PER_DAY,
        priority=10,
        reads=("government", "economy", "agents", "geography", "companies", "population"),
        writes=("government", "economy", "agents", "geography"),
        emits=(Topics.GOV_POLICY, Topics.GOV_EMERGENCY, Topics.GOV_BUDGET, Topics.GOV_ELECTION),
        description="Daily policy decisions from economy, unrest, approval and fiscal position.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        government = ctx.state.domain(GovernmentState)
        economy = ctx.state.domain(EconomyState)
        agents = ctx.state.domain(AgentsState)
        geography = ctx.state.domain(GeographyState)
        rng = ctx.rng("government")

        treasury = economy.balance(government.treasury_account_id)
        energy_market = economy.markets["electricity"]
        energy_trend = self._trend(energy_market.price_history, 144)
        food_trend = self._trend(economy.markets["food"].price_history, 144)
        unemployment = economy.unemployment_rate
        inflation = economy.inflation_annual
        unrest = government.unrest_index
        party = government.parties.get(government.ruling_party_id)
        ideology = party.ideology if party else {"market": 0.5, "authority": 0.5, "welfare": 0.5, "green": 0.4}

        self._public_sector(ctx, government, economy, agents)
        self._pay_active_policies(ctx, government, economy)
        self._update_approval(government, agents, unemployment, inflation, unrest)

        decision = None
        if ctx.tick < POLICY_WARMUP_TICKS:
            decision = None
        elif energy_trend > ENERGY_TREND_TRIGGER and (unrest > 0.12 or energy_trend > ENERGY_SPIKE_TRIGGER):
            decision = (
                PolicyKind.PRICE_CAP if ideology.get("authority", 0.5) > 0.6 else PolicyKind.ENERGY_SUBSIDY
            )
        elif food_trend > FOOD_TREND_TRIGGER:
            decision = PolicyKind.PRICE_CAP if ideology.get("authority", 0.5) > 0.65 else PolicyKind.WELFARE_BOOST
        elif ctx.tick >= POLICY_WARMUP_TICKS and unemployment > 0.10:
            decision = PolicyKind.PUBLIC_WORKS if ideology.get("welfare", 0.5) > 0.45 else PolicyKind.TAX_CHANGE
        elif unrest > 0.30:
            decision = PolicyKind.POLICING_SURGE if ideology.get("authority", 0.5) > 0.55 else PolicyKind.WELFARE_BOOST
        elif treasury < 0 and government.debt_minor > 500_000_000:
            decision = PolicyKind.AUSTERITY
        elif inflation > 0.10:
            decision = PolicyKind.TAX_CHANGE

        if decision is not None and government.policy_of_kind(decision) is None:
            if ctx.tick - government.last_decision_tick >= TICKS_PER_DAY * 2:
                self._enact(ctx, government, economy, decision, rng, treasury)

        self._expire(ctx, government)
        self._emergency(ctx, government, geography, unrest)
        self._maybe_election(ctx, government, agents, rng)

        ctx.telemetry.gauge("gov_approval", government.approval)
        ctx.telemetry.gauge("gov_treasury_minor", float(treasury))
        ctx.telemetry.gauge("gov_debt_minor", float(government.debt_minor))
        ctx.telemetry.gauge("active_policies", float(len(government.active_policies())))

    @staticmethod
    def _public_sector(ctx, government: GovernmentState, economy: EconomyState, agents: AgentsState) -> None:  # noqa: ANN001
        """Pay the public payroll and buy what the city runs on.

        Taxes that are collected and never spent are a hole in the economy: firms pay wages,
        the state takes a share, and if that share never comes back, every firm is structurally
        loss-making. This is the return leg.
        """

        from hydra.economy.clearing import purchase

        treasury = government.treasury_account_id
        wage = government.public_wage_minor
        paid = 0
        for cohort_id in sorted(government.public_jobs):
            cohort = agents.cohorts.get(cohort_id)
            headcount = government.public_jobs[cohort_id]
            if cohort is None or headcount <= 0:
                continue
            gross = int(wage / 30.0) * headcount
            tax = int(gross * government.income_tax_rate)
            net = gross - tax
            if not cohort.account_id:
                continue
            # Wages are a transfer, never an entry: the treasury must actually have the money.
            if not transfer(economy, treasury, cohort.account_id, net):
                break
            cohort.savings_minor = economy.balance(cohort.account_id)
            cohort.daily_income_minor += net
            paid += gross
        government.spending_ytd_minor += paid

        # Procurement: the city buys services, care and teaching like any other customer.
        budget = max(0, int(economy.balance(treasury) * 0.04))
        procured = 0
        for code, share in (("services", 0.4), ("healthcare", 0.25), ("education", 0.2), ("transport", 0.15)):
            market = economy.markets.get(code)
            if market is None:
                continue
            quantity = (budget * share) / max(1, market.price_minor)
            if quantity <= 0:
                continue
            market.demand += quantity
            bought = purchase(
                economy,
                buyer_account_id=treasury,
                code=code,
                quantity=quantity,
                allow_import=False,
            )
            procured += bought.spent_minor
        government.procurement_yesterday_minor = procured
        government.spending_ytd_minor += procured
        ctx.telemetry.gauge("public_wages_minor", float(paid))
        ctx.telemetry.gauge("public_procurement_minor", float(procured))

    # -- helpers ------------------------------------------------------------------
    @staticmethod
    def _trend(history: list[int], window: int) -> float:
        if len(history) < 4:
            return 0.0
        recent = history[-1]
        past = history[-min(len(history), window)]
        return (recent - past) / max(1, past)

    @staticmethod
    def _update_approval(government: GovernmentState, agents: AgentsState, unemployment: float,
                         inflation: float, unrest: float) -> None:
        population = max(1, agents.cohort_population())
        trust = sum(c.trust_government * c.size for c in agents.cohorts.values()) / population
        target = max(
            0.02,
            min(0.98, 0.55 * trust + 0.45 * (0.75 - unemployment * 2.2 - max(0.0, inflation) * 0.9 - unrest * 0.8)),
        )
        government.approval = round(0.9 * government.approval + 0.1 * target, 5)
        government.public_support_history.append(government.approval)
        del government.public_support_history[:-720]

    def _enact(self, ctx, government: GovernmentState, economy: EconomyState, kind: PolicyKind, rng, treasury: int) -> None:  # noqa: ANN001
        government.next_policy_index += 1
        policy_id = f"policy_{government.next_policy_index:05d}"
        value = 0.0
        cost = 0
        target = ""
        label = kind.value.replace("_", " ")

        if kind is PolicyKind.ENERGY_SUBSIDY:
            value = round(rng.uniform(0.08, 0.22), 4)
            target = "electricity"
            daily_kwh = ctx.state.domain(GeographyState).city().infrastructure.power_demand_mw * 1000.0 * 24.0
            cost = int(daily_kwh * economy.markets["electricity"].price_minor * value)
        elif kind is PolicyKind.PRICE_CAP:
            target = "electricity" if self._trend(economy.markets["electricity"].price_history, 144) > 0.1 else "food"
            # The cap is an absolute price, so the market can enforce it without re-deriving it.
            # A cap is a ceiling over today's price, not a freeze at it.
            value = float(int(economy.markets[target].price_minor * rng.uniform(1.10, 1.25)))
        elif kind is PolicyKind.WELFARE_BOOST:
            value = round(rng.uniform(0.15, 0.4), 4)
            government.welfare_per_day_minor = int(government.welfare_per_day_minor * (1.0 + value))
            cost = int(government.welfare_per_day_minor * 0.2)
        elif kind is PolicyKind.PUBLIC_WORKS:
            value = round(rng.uniform(0.02, 0.06), 4)
            cost = int(max(2_000_000, abs(treasury) * 0.01))
        elif kind is PolicyKind.TAX_CHANGE:
            value = round(-rng.uniform(0.01, 0.03), 4)
            government.vat_rate = round(max(0.05, government.vat_rate + value), 4)
        elif kind is PolicyKind.POLICING_SURGE:
            value = round(rng.uniform(0.1, 0.3), 4)
            cost = int(government.institutions["gov_police"].budget_minor * 0.01)
        elif kind is PolicyKind.AUSTERITY:
            value = round(-rng.uniform(0.1, 0.25), 4)
            government.welfare_per_day_minor = int(government.welfare_per_day_minor * (1.0 + value))

        policy = Policy(
            policy_id=policy_id,
            kind=kind,
            label=label,
            value=value,
            enacted_tick=ctx.tick,
            expires_tick=ctx.tick + TICKS_PER_DAY * rng.randint(20, 90),
            cost_per_day_minor=cost,
            proposer_id=government.mayor_id,
            support_at_enactment=government.approval,
            target=target,
            rationale=f"response to {kind.value}",
        )
        government.policies[policy_id] = policy
        government.last_decision_tick = ctx.tick
        government.decision_log.append(f"t{ctx.tick} {kind.value} value={value}")
        del government.decision_log[:-40]

        ctx.emit(
            Topics.GOV_POLICY,
            "enacted_policy",
            actor=government.mayor_id or "gov_city",
            target=policy_id,
            payload={
                "policy": kind.value,
                "value": value,
                "cost_per_day_minor": cost,
                "target": target,
                "approval": government.approval,
            },
            inputs=ImportanceInputs(
                people_affected=ctx.state.domain(AgentsState).total_population() * 0.7,
                economic_impact=cost * 30,
                political_impact=0.75,
                risk=0.2,
                novelty=0.6,
            ),
        )

    @staticmethod
    def _pay_active_policies(ctx, government: GovernmentState, economy: EconomyState) -> None:  # noqa: ANN001
        for policy in government.active_policies():
            if policy.cost_per_day_minor <= 0:
                continue
            if not transfer(economy, government.treasury_account_id, economy.escrow_account_id, policy.cost_per_day_minor):
                # The city borrows rather than defaulting on its own policy: the money still
                # moves, the debt is what pays for it.
                treasury_account = economy.accounts[government.treasury_account_id]
                treasury_account.overdraft_minor += policy.cost_per_day_minor
                if transfer(economy, government.treasury_account_id, economy.escrow_account_id, policy.cost_per_day_minor):
                    government.debt_minor += policy.cost_per_day_minor
                else:
                    continue
            government.spending_ytd_minor += policy.cost_per_day_minor

    @staticmethod
    def _expire(ctx, government: GovernmentState) -> None:  # noqa: ANN001
        for policy in government.policies.values():
            if policy.active and policy.expires_tick is not None and ctx.tick >= policy.expires_tick:
                policy.active = False
                if policy.kind is PolicyKind.WELFARE_BOOST:
                    government.welfare_per_day_minor = int(government.welfare_per_day_minor / (1.0 + policy.value))

    @staticmethod
    def _emergency(ctx, government: GovernmentState, geography: GeographyState, unrest: float) -> None:  # noqa: ANN001
        level = 0
        if unrest > 0.45:
            level = 2
        elif unrest > 0.3:
            level = 1
        city = geography.city()
        if city.infrastructure.power_output_mw < city.infrastructure.power_demand_mw * 0.85:
            level = max(level, 2)
        if level != government.emergency_level:
            government.emergency_level = level
            if level > 0:
                ctx.emit(
                    Topics.GOV_EMERGENCY,
                    "emergency_declared",
                    actor=government.mayor_id or "gov_city",
                    payload={"level": level, "unrest": unrest},
                    inputs=ImportanceInputs(
                        people_affected=ctx.state.domain(AgentsState).total_population(),
                        political_impact=0.9,
                        risk=0.7,
                        novelty=0.7,
                    ),
                )

    def _maybe_election(self, ctx, government: GovernmentState, agents: AgentsState, rng) -> None:  # noqa: ANN001
        if not government.elections:
            government.elections.append(
                Election(election_id="election_0001", scheduled_tick=ELECTION_PERIOD_TICKS)
            )
        election = government.elections[-1]
        if election.held or ctx.tick < election.scheduled_tick:
            return

        population = max(1, agents.cohort_population())
        satisfaction = sum(c.trust_government * c.size for c in agents.cohorts.values()) / population
        results: dict[str, float] = {}
        for party_id in sorted(government.parties):
            party = government.parties[party_id]
            incumbent_bonus = satisfaction - 0.5 if party.in_power else (0.5 - satisfaction) * 0.6
            noise = rng.uniform(-0.06, 0.06)
            results[party_id] = max(0.01, party.support + incumbent_bonus * 0.35 + noise)
        total = sum(results.values())
        for party_id, score in results.items():
            government.parties[party_id].support = round(score / total, 5)
            government.parties[party_id].in_power = False
        winner = max(results, key=lambda p: (results[p], p))
        government.parties[winner].in_power = True
        government.ruling_party_id = winner
        new_mayor = government.parties[winner].leader_id
        if new_mayor:
            government.mayor_id = new_mayor
            government.institutions["gov_city"].leader_id = new_mayor
        election.held = True
        election.winner_party_id = winner
        election.turnout = round(min(0.95, 0.45 + satisfaction * 0.4), 4)
        election.results = {k: round(v / total, 5) for k, v in results.items()}
        government.elections.append(
            Election(
                election_id=f"election_{len(government.elections) + 1:04d}",
                scheduled_tick=ctx.tick + ELECTION_PERIOD_TICKS,
            )
        )
        ctx.emit(
            Topics.GOV_ELECTION,
            "election_held",
            actor="gov_council",
            target=winner,
            payload={
                "winner": government.parties[winner].name,
                "turnout": election.turnout,
                "results": election.results,
            },
            inputs=ImportanceInputs(
                people_affected=agents.total_population(),
                political_impact=1.0,
                novelty=0.9,
            ),
        )


class TaxSystem:
    spec = SystemSpec(
        name="taxes",
        phase=Phase.INSTITUTIONS,
        cadence_ticks=TICKS_PER_DAY,
        priority=60,
        reads=("government", "economy", "companies"),
        writes=("government", "economy", "companies"),
        emits=(Topics.GOV_BUDGET,),
        description="Monthly corporate tax, budget balance and public debt.",
    )

    def step(self, ctx) -> None:  # noqa: ANN001
        if ctx.now.day != 1:
            return
        from hydra.companies.model import CompaniesState

        government = ctx.state.domain(GovernmentState)
        economy = ctx.state.domain(EconomyState)
        companies = ctx.state.domain(CompaniesState)
        collected = 0
        for company in companies.active():
            profit = sum(company.profit_history[-30:])
            if profit <= 0:
                continue
            due = int(profit * government.corporate_tax_rate)
            if transfer(economy, company.account_id, government.treasury_account_id, due):
                collected += due
        government.revenue_ytd_minor += collected
        balance = economy.balance(government.treasury_account_id)
        if balance < 0:
            government.debt_minor += -balance
        ctx.emit(
            Topics.GOV_BUDGET,
            "budget_update",
            actor="gov_tax",
            payload={
                "corporate_tax_minor": collected,
                "treasury_minor": balance,
                "debt_minor": government.debt_minor,
                "revenue_ytd_minor": government.revenue_ytd_minor,
                "spending_ytd_minor": government.spending_ytd_minor,
            },
            importance=0.18,
        )
