"""Action handlers — the only place agent intent becomes world change.

Flow per spec section 36:

    Agent Brain → Action Intent → Validator → World Rules → Resource Check → Execute → Event

Each handler validates against the real world (does the shop exist, is there stock, can they
pay, are they in the right place) before anything mutates. A rejected action is a normal
outcome and produces its own event.
"""

from __future__ import annotations

from hydra.companies.model import CompaniesState, Company, Sector, Strategy
from hydra.economy.clearing import purchase
from hydra.economy.model import EconomyState, OwnerKind
from hydra.events.importance import ImportanceInputs
from hydra.events.model import Topics, TruthStatus, Visibility
from hydra.geography.model import GeographyState
from hydra.government.model import GovernmentState
from hydra.information.model import KnowledgeState, KnownFact, Observation, Source
from hydra.information.net import NetState, Post, SiteKind
from hydra.kernel.actions import ActionIntent, ActionPipeline, ActionResult
from hydra.kernel.errors import ActionRejected
from hydra.kernel.ids import company_id as make_company_id
from hydra.media.model import MediaState
from hydra.memory.model import MemoryKind, MemoryState
from hydra.memory.operations import record as record_memory
from hydra.population.model import PopulationState
from hydra.social.model import Relation, SocialState

from .model import Activity, AgentsState, Employment, Person, Tier


def _person(ctx, intent: ActionIntent) -> Person:  # noqa: ANN001
    agents = ctx.state.domain(AgentsState)
    person = agents.people.get(intent.actor)
    if person is None:
        raise ActionRejected("unknown_actor", intent.actor)
    if not person.alive:
        raise ActionRejected("actor_dead", intent.actor)
    if person.activity is Activity.SLEEP:
        raise ActionRejected("actor_asleep", intent.actor)
    return person


def _remember(ctx, person: Person, topic: str, summary: str, salience: float, valence: float = 0.0) -> None:  # noqa: ANN001
    record_memory(
        ctx.state.domain(MemoryState),
        person.person_id,
        tick=ctx.tick,
        topic=topic,
        summary=summary,
        salience=salience,
        valence=valence,
        working_limit=ctx.config.information.max_working_memory,
    )


class RestHandler:
    action = "rest"

    def validate(self, ctx, intent: ActionIntent) -> None:  # noqa: ANN001
        _person(ctx, intent)

    def execute(self, ctx, intent: ActionIntent) -> ActionResult:  # noqa: ANN001
        person = _person(ctx, intent)
        person.energy = round(min(1.0, person.energy + 0.09), 4)
        person.stress = round(max(0.0, person.stress - 0.05), 4)
        person.needs.rest = round(min(1.0, person.needs.rest + 0.12), 4)
        person.location_building_id = person.home_building_id
        person.note_action("rested")
        return ActionResult(intent=intent, accepted=True, outcome={"energy": person.energy})


class GoToWorkHandler:
    action = "go_to_work"

    def validate(self, ctx, intent: ActionIntent) -> None:  # noqa: ANN001
        person = _person(ctx, intent)
        if not person.employer_id:
            raise ActionRejected("no_employer", person.person_id)
        companies = ctx.state.domain(CompaniesState)
        company = companies.companies.get(person.employer_id)
        if company is None or company.bankrupt:
            raise ActionRejected("employer_gone", person.employer_id)

    def execute(self, ctx, intent: ActionIntent) -> ActionResult:  # noqa: ANN001
        person = _person(ctx, intent)
        companies = ctx.state.domain(CompaniesState)
        company = companies.companies[person.employer_id]
        geography = ctx.state.domain(GeographyState)
        district = geography.districts.get(company.district_id)
        person.location_building_id = company.building_id
        person.energy = round(max(0.0, person.energy - 0.06), 4)
        commute_stress = 0.02 if district is None else 0.01 + district.transport_load * 0.02
        person.stress = round(min(1.0, person.stress + commute_stress), 4)
        person.needs.purpose = round(min(1.0, person.needs.purpose + 0.03), 4)
        person.note_action("went to work")

        # Being at work is how workers learn about their employer's condition.
        if company.months_of_loss >= 2:
            knowledge = ctx.state.domain(KnowledgeState)
            fact_id = f"fact_company_{company.company_id}_stress"
            if fact_id in knowledge.facts:
                knowledge.learn(
                    person.person_id,
                    KnownFact(fact_id=fact_id, acquired_tick=ctx.tick, source=Source.WORK, confidence=0.8,
                              value=float(company.months_of_loss)),
                )
        return ActionResult(intent=intent, accepted=True, outcome={"at": company.building_id})


class BuyFoodHandler:
    action = "buy_food"

    def validate(self, ctx, intent: ActionIntent) -> None:  # noqa: ANN001
        person = _person(ctx, intent)
        economy = ctx.state.domain(EconomyState)
        market = economy.markets.get("food")
        if market is None:
            raise ActionRejected("no_market", "food")
        population = ctx.state.domain(PopulationState)
        household = population.households.get(person.household_id)
        account_id = household.account_id if household else person.account_id
        quantity = float(intent.params.get("quantity", 1.0))
        cost = market.price_minor * quantity
        if economy.accounts[account_id].available() < cost:
            raise ActionRejected("insufficient_funds", f"food×{quantity}")

    def execute(self, ctx, intent: ActionIntent) -> ActionResult:  # noqa: ANN001
        person = _person(ctx, intent)
        economy = ctx.state.domain(EconomyState)
        government = ctx.state.domain(GovernmentState)
        population = ctx.state.domain(PopulationState)
        household = population.households.get(person.household_id)
        account_id = household.account_id if household else person.account_id
        quantity = float(intent.params.get("quantity", 1.0))
        economy.markets["food"].demand += quantity
        bought = purchase(
            economy,
            buyer_account_id=account_id,
            code="food",
            quantity=quantity,
            vat_rate=government.vat_rate,
            treasury_account_id=government.treasury_account_id,
        )
        if bought.filled <= 0.0:
            raise ActionRejected("out_of_stock", "food")
        person.needs.food = round(min(1.0, person.needs.food + 0.25 * bought.filled), 4)
        if household is not None:
            household.food_stock = round(household.food_stock + bought.filled, 4)
        person.note_action("bought food")
        # People notice prices when they pay them. This is the main honest price channel.
        knowledge = ctx.state.domain(KnowledgeState)
        fact_id = "fact_genesis_price_food"
        if fact_id in knowledge.facts:
            knowledge.learn(
                person.person_id,
                KnownFact(fact_id=fact_id, acquired_tick=ctx.tick, source=Source.OBSERVED, confidence=0.95,
                          value=float(economy.markets["food"].price_minor)),
            )
        return ActionResult(intent=intent, accepted=True,
                            outcome={"filled": bought.filled, "spent_minor": bought.spent_minor})


class BuyItemHandler:
    """Generic purchase, the spec's worked example: shop, stock, money, location."""

    action = "buy_item"

    def validate(self, ctx, intent: ActionIntent) -> None:  # noqa: ANN001
        person = _person(ctx, intent)
        economy = ctx.state.domain(EconomyState)
        code = str(intent.params.get("item", ""))
        quantity = float(intent.params.get("quantity", 1))
        market = economy.markets.get(code)
        if market is None:
            raise ActionRejected("unknown_item", code)
        good = economy.goods[code]
        if good.storable and market.inventory < quantity:
            raise ActionRejected("out_of_stock", code)
        if economy.accounts[person.account_id].available() < market.price_minor * quantity:
            raise ActionRejected("insufficient_funds", code)
        geography = ctx.state.domain(GeographyState)
        district = geography.districts.get(person.district_id)
        if district is None:
            raise ActionRejected("invalid_location", person.district_id)

    def execute(self, ctx, intent: ActionIntent) -> ActionResult:  # noqa: ANN001
        person = _person(ctx, intent)
        economy = ctx.state.domain(EconomyState)
        government = ctx.state.domain(GovernmentState)
        code = str(intent.params["item"])
        quantity = float(intent.params.get("quantity", 1))
        economy.markets[code].demand += quantity
        bought = purchase(
            economy,
            buyer_account_id=person.account_id,
            code=code,
            quantity=quantity,
            vat_rate=government.vat_rate,
            treasury_account_id=government.treasury_account_id,
        )
        person.note_action(f"bought {code}")
        return ActionResult(intent=intent, accepted=True,
                            outcome={"filled": bought.filled, "spent_minor": bought.spent_minor})


class LookForJobHandler:
    action = "look_for_job"

    def validate(self, ctx, intent: ActionIntent) -> None:  # noqa: ANN001
        person = _person(ctx, intent)
        if person.employment in (Employment.EMPLOYED, Employment.PUBLIC):
            raise ActionRejected("already_employed", person.person_id)

    def execute(self, ctx, intent: ActionIntent) -> ActionResult:  # noqa: ANN001
        person = _person(ctx, intent)
        companies = ctx.state.domain(CompaniesState)
        rng = ctx.rng("job_search", person.person_id)
        local = [
            o for o in companies.openings.values()
            if o.positions > o.filled
            and companies.companies.get(o.company_id)
            and companies.companies[o.company_id].district_id == person.district_id
        ]
        person.energy = round(max(0.0, person.energy - 0.04), 4)
        person.note_action("looked for work")
        if not local:
            person.stress = round(min(1.0, person.stress + 0.02), 4)
            _remember(ctx, person, "job_search", "found no openings nearby", 0.35, -0.2)
            return ActionResult(intent=intent, accepted=True, outcome={"found": 0})
        opening = rng.choice(sorted(local, key=lambda o: o.opening_id))
        _remember(ctx, person, "job_search", f"spotted an opening at {opening.company_id}", 0.4, 0.15)
        return ActionResult(intent=intent, accepted=True, outcome={"found": len(local), "opening": opening.opening_id})


class ApplyForJobHandler:
    action = "apply_for_job"

    def validate(self, ctx, intent: ActionIntent) -> None:  # noqa: ANN001
        person = _person(ctx, intent)
        if person.employment in (Employment.EMPLOYED, Employment.PUBLIC):
            raise ActionRejected("already_employed", person.person_id)
        companies = ctx.state.domain(CompaniesState)
        opening = companies.openings.get(str(intent.params.get("opening_id", "")))
        if opening is None:
            raise ActionRejected("opening_gone", str(intent.params.get("opening_id")))
        if opening.filled >= opening.positions:
            raise ActionRejected("opening_filled", opening.opening_id)
        company = companies.companies.get(opening.company_id)
        if company is None or company.bankrupt:
            raise ActionRejected("employer_gone", opening.company_id)

    def execute(self, ctx, intent: ActionIntent) -> ActionResult:  # noqa: ANN001
        person = _person(ctx, intent)
        companies = ctx.state.domain(CompaniesState)
        opening = companies.openings[str(intent.params["opening_id"])]
        company = companies.companies[opening.company_id]
        rng = ctx.rng("job_application", person.person_id)
        skill = person.skills.get(opening.skill, 0.4)
        chance = 0.25 + max(-0.4, min(0.5, skill - opening.skill_required)) + person.reputation * 0.2
        if not rng.chance(max(0.05, min(0.9, chance))):
            person.stress = round(min(1.0, person.stress + 0.04), 4)
            _remember(ctx, person, "job_search", f"rejected by {company.name}", 0.5, -0.35)
            return ActionResult(intent=intent, accepted=True, outcome={"hired": False})

        person.employer_id = company.company_id
        person.employment = Employment.EMPLOYED
        person.work_building_id = company.building_id
        person.wage_minor = int(opening.wage_minor * (0.85 + 0.3 * skill))
        person.stress = round(max(0.0, person.stress - 0.15), 4)
        person.mood = round(min(1.0, person.mood + 0.15), 4)
        company.employee_ids.append(person.person_id)
        company.hires_total += 1
        opening.filled += 1
        companies.total_hires += 1
        if opening.filled >= opening.positions:
            companies.openings.pop(opening.opening_id, None)
        ctx.state.domain(SocialState).link(
            person.person_id, company.company_id, Relation.WORKS_FOR, tick=ctx.tick, strength=0.5, trust=0.5
        )
        _remember(ctx, person, "job_search", f"hired by {company.name}", 0.85, 0.6)
        event = ctx.emit(
            Topics.PERSON_HIRED,
            "hired",
            actor=person.person_id,
            target=company.company_id,
            location=company.district_id,
            payload={"wage_minor": person.wage_minor, "role": opening.role, "company_name": company.name},
            inputs=ImportanceInputs(people_affected=2.4, economic_impact=person.wage_minor, proximity=0.5),
        )
        return ActionResult(intent=intent, accepted=True, event_id=event.event_id, outcome={"hired": True})


class SocialiseHandler:
    """Talking is how information moves between people — and how it gets distorted."""

    action = "socialise"

    def validate(self, ctx, intent: ActionIntent) -> None:  # noqa: ANN001
        _person(ctx, intent)

    def execute(self, ctx, intent: ActionIntent) -> ActionResult:  # noqa: ANN001
        person = _person(ctx, intent)
        social = ctx.state.domain(SocialState)
        knowledge = ctx.state.domain(KnowledgeState)
        agents = ctx.state.domain(AgentsState)
        rng = ctx.rng("socialise", person.person_id)
        edges = [
            e for e in social.neighbours(person.person_id)
            if e.target.startswith("person_") and e.target in agents.people
        ]
        person.needs.social = round(min(1.0, person.needs.social + 0.18), 4)
        person.mood = round(min(1.0, person.mood + 0.03), 4)
        person.note_action("talked with someone")
        if not edges:
            return ActionResult(intent=intent, accepted=True, outcome={"partner": None})

        edge = rng.weighted_choice(sorted(edges, key=lambda e: e.edge_id), [max(0.05, e.strength) for e in edges])
        other = agents.people[edge.target]
        edge.interactions += 1
        edge.last_interaction_tick = ctx.tick
        edge.adjust(ctx.tick, field_name="strength", delta=0.02, reason="conversation")

        shared = None
        known = knowledge.known(person.person_id)
        if known:
            fact_id = rng.choice(sorted(known))
            known_fact = known[fact_id]
            if known_fact.confidence > 0.3:
                distort = rng.chance(ctx.config.information.rumour_distortion_probability)
                value = known_fact.value * (rng.uniform(0.75, 1.3) if distort else 1.0)
                knowledge.learn(
                    other.person_id,
                    KnownFact(
                        fact_id=fact_id,
                        acquired_tick=ctx.tick,
                        source=Source.SOCIAL,
                        confidence=round(known_fact.confidence * edge.trust * 0.9, 4),
                        value=round(value, 3),
                        distorted=distort,
                        believed_truth=TruthStatus.DISTORTED if distort else TruthStatus.UNVERIFIED,
                        via=person.person_id,
                    ),
                )
                fact = knowledge.facts.get(fact_id)
                knowledge.observe(
                    other.person_id,
                    Observation(
                        tick=ctx.tick,
                        kind="fact",
                        topic=fact.topic if fact else "talk",
                        summary=f"{person.name} said: {fact.text if fact else fact_id}",
                        importance=0.15,
                        fact_id=fact_id,
                        source=Source.SOCIAL,
                        via=person.person_id,
                    ),
                )
                knowledge.spread_events += 1
                if distort:
                    knowledge.distortions += 1
                shared = fact_id
        return ActionResult(intent=intent, accepted=True, outcome={"partner": other.person_id, "shared": shared})


class ReadNewsHandler:
    action = "read_news"

    def validate(self, ctx, intent: ActionIntent) -> None:  # noqa: ANN001
        _person(ctx, intent)

    def execute(self, ctx, intent: ActionIntent) -> ActionResult:  # noqa: ANN001
        person = _person(ctx, intent)
        media = ctx.state.domain(MediaState)
        knowledge = ctx.state.domain(KnowledgeState)
        rng = ctx.rng("read_news", person.person_id)
        outlets = sorted(media.outlets.values(), key=lambda o: o.outlet_id)
        if not outlets:
            return ActionResult(intent=intent, accepted=True, outcome={"read": 0})

        # Which outlet someone reads is itself a belief-driven choice.
        weights = []
        for outlet in outlets:
            alignment = 1.0 - abs(outlet.bias_government - (person.political_trust * 2.0 - 1.0)) / 2.0
            weights.append(max(0.05, outlet.audience_share * (0.4 + alignment)))
        outlet = rng.weighted_choice(outlets, weights)
        publications = [p for p in media.publications.values() if p.outlet_id == outlet.outlet_id]
        publications.sort(key=lambda p: -p.tick)
        read = 0
        for publication in publications[:3]:
            fact = knowledge.facts.get(publication.fact_id)
            if fact is None:
                continue
            accurate = rng.chance(outlet.accuracy)
            value = fact.value if accurate else fact.value * rng.uniform(0.7, 1.4)
            knowledge.learn(
                person.person_id,
                KnownFact(
                    fact_id=fact.fact_id,
                    acquired_tick=ctx.tick,
                    source=Source.MEDIA,
                    confidence=round(min(0.95, 0.35 + outlet.reputation * 0.6), 4),
                    value=round(value, 3),
                    distorted=not accurate,
                    believed_truth=TruthStatus.TRUE if accurate else TruthStatus.DISTORTED,
                    via=outlet.outlet_id,
                ),
            )
            belief = knowledge.belief(person.person_id, publication.topic)
            rate = ctx.config.information.belief_update_rate * (0.4 + outlet.reputation * 0.6)
            belief.position = round(max(-1.0, min(1.0, belief.position * (1 - rate) + publication.sentiment * rate)), 4)
            belief.confidence = round(min(1.0, belief.confidence + 0.08), 4)
            belief.updated_tick = ctx.tick
            if fact.fact_id not in belief.based_on:
                belief.based_on.append(fact.fact_id)
                del belief.based_on[:-8]
            if publication.framing == "blame_government":
                person.political_trust = round(max(0.0, person.political_trust - 0.02 * outlet.reputation), 4)
            elif publication.framing == "reassure":
                person.political_trust = round(min(1.0, person.political_trust + 0.012 * outlet.reputation), 4)
            read += 1
        outlet.reach += 1
        person.note_action(f"read {outlet.name}")
        if read:
            _remember(ctx, person, "news", f"read {read} stories in {outlet.name}", 0.3)
        return ActionResult(intent=intent, accepted=True, outcome={"read": read, "outlet": outlet.outlet_id})


class PostOnlineHandler:
    """An agent may only post what it actually knows — subjective knowledge is enforced here."""

    action = "post_online"

    def validate(self, ctx, intent: ActionIntent) -> None:  # noqa: ANN001
        person = _person(ctx, intent)
        knowledge = ctx.state.domain(KnowledgeState)
        fact_id = str(intent.params.get("fact_id", ""))
        if not knowledge.knows(person.person_id, fact_id):
            raise ActionRejected("unknown_fact", fact_id)
        net = ctx.state.domain(NetState)
        if not net.sites:
            raise ActionRejected("no_sites", "hydranet is empty")

    def execute(self, ctx, intent: ActionIntent) -> ActionResult:  # noqa: ANN001
        person = _person(ctx, intent)
        net = ctx.state.domain(NetState)
        knowledge = ctx.state.domain(KnowledgeState)
        rng = ctx.rng("post", person.person_id)
        fact_id = str(intent.params["fact_id"])
        known = knowledge.known(person.person_id)[fact_id]
        fact = knowledge.facts.get(fact_id)
        social_sites = net.sites_of_kind(SiteKind.SOCIAL) or list(net.sites.values())
        site = rng.choice(sorted(social_sites, key=lambda s: s.site_id))
        stance = round(max(-1.0, min(1.0, (person.political_trust - 0.5) * 2.0 + rng.uniform(-0.3, 0.3))), 3)
        text = fact.text if fact else fact_id
        if known.distorted:
            text = f"heard that {text}"
        post = Post(
            post_id=net.new_post_id(),
            site_id=site.site_id,
            author_id=person.person_id,
            tick=ctx.tick,
            topic=fact.topic if fact else "misc",
            text=text,
            fact_id=fact_id,
            stance=stance,
            reach=int(site.reach * 400 * (0.4 + person.reputation)),
            truth=known.believed_truth,
        )
        net.add_post(post)
        net.trending[post.topic] = round(net.trending.get(post.topic, 0.0) + 1.0, 3)
        person.note_action("posted online")
        event = ctx.emit(
            Topics.NET_POST,
            "posted",
            actor=person.person_id,
            target=site.site_id,
            location=person.district_id,
            payload={"topic": post.topic, "fact_id": fact_id, "reach": post.reach, "stance": stance},
            inputs=ImportanceInputs(people_affected=post.reach * 0.2, political_impact=abs(stance) * 0.2),
        )
        return ActionResult(intent=intent, accepted=True, event_id=event.event_id, outcome={"post_id": post.post_id})


class ProtestHandler:
    action = "protest"

    def validate(self, ctx, intent: ActionIntent) -> None:  # noqa: ANN001
        person = _person(ctx, intent)
        if person.age_years < 16:
            raise ActionRejected("too_young", person.person_id)
        geography = ctx.state.domain(GeographyState)
        if person.district_id not in geography.districts:
            raise ActionRejected("invalid_location", person.district_id)

    def execute(self, ctx, intent: ActionIntent) -> ActionResult:  # noqa: ANN001
        person = _person(ctx, intent)
        geography = ctx.state.domain(GeographyState)
        government = ctx.state.domain(GovernmentState)
        district = geography.districts[person.district_id]
        district.unrest = round(min(1.0, district.unrest + 0.01), 4)
        government.protests_active += 1
        person.stress = round(min(1.0, person.stress + 0.05), 4)
        person.energy = round(max(0.0, person.energy - 0.1), 4)
        person.note_action("joined a protest")
        _remember(ctx, person, "protest", f"protested in {district.name}", 0.7, -0.1)
        event = ctx.emit(
            Topics.PERSON_PROTEST,
            "joined_protest",
            actor=person.person_id,
            location=district.district_id,
            payload={"district": district.name, "trust": person.political_trust},
            inputs=ImportanceInputs(people_affected=40, political_impact=0.45, risk=0.25, proximity=0.5),
            visibility=Visibility.PUBLIC,
        )
        return ActionResult(intent=intent, accepted=True, event_id=event.event_id)


class FoundCompanyHandler:
    action = "found_company"

    MIN_CAPITAL_MINOR = 3_000_000

    def validate(self, ctx, intent: ActionIntent) -> None:  # noqa: ANN001
        person = _person(ctx, intent)
        economy = ctx.state.domain(EconomyState)
        if economy.balance(person.account_id) < self.MIN_CAPITAL_MINOR:
            raise ActionRejected("insufficient_capital", person.person_id)
        if person.age_years < 21:
            raise ActionRejected("too_young", person.person_id)

    def execute(self, ctx, intent: ActionIntent) -> ActionResult:  # noqa: ANN001
        person = _person(ctx, intent)
        economy = ctx.state.domain(EconomyState)
        companies = ctx.state.domain(CompaniesState)
        geography = ctx.state.domain(GeographyState)
        rng = ctx.rng("found_company", person.person_id)

        # Founders go where margins are: the sector with the widest price-to-cost gap.
        best_code, best_margin = "services", -1.0
        for code, market in economy.markets.items():
            if code not in economy.recipes:
                continue
            margin = (market.price_minor - market.unit_cost_minor) / max(1, market.price_minor)
            if margin > best_margin:
                best_code, best_margin = code, margin

        companies.next_company_index += 1
        company_id = make_company_id(companies.next_company_index)
        capital = int(economy.balance(person.account_id) * 0.6)
        account = economy.open_account(company_id, OwnerKind.COMPANY, balance_minor=0, overdraft_minor=capital // 4)
        from hydra.economy.money import transfer

        transfer(economy, person.account_id, account.account_id, capital)
        district = geography.districts[person.district_id]
        building = rng.choice(district.building_ids)
        sector = _sector_for_product(best_code)
        company = Company(
            company_id=company_id,
            name=f"{person.name.split()[-1]} {sector.value.title()}",
            sector=sector,
            district_id=person.district_id,
            building_id=building,
            account_id=account.account_id,
            product_code=best_code,
            recipe_code=best_code,
            founded_tick=ctx.tick,
            owner_ids=[person.person_id],
            capacity_units=round(capital / 3_000.0, 2),
            utilisation=0.6,
            price_minor=economy.markets[best_code].price_minor,
            unit_cost_minor=economy.markets[best_code].unit_cost_minor,
            average_wage_minor=int(economy.wage_index * 300_000),
            technology=round(min(1.0, 0.3 + person.education * 0.5), 4),
            strategy=Strategy.GROW,
        )
        companies.companies[company_id] = company
        companies.foundations += 1
        person.employer_id = company_id
        person.employment = Employment.SELF_EMPLOYED
        person.occupation = f"founder of {company.name}"
        person.importance = round(min(1.0, person.importance + 0.15), 4)
        ctx.state.domain(SocialState).link(person.person_id, company_id, Relation.OWNS, tick=ctx.tick, strength=1.0, trust=1.0)
        _remember(ctx, person, "career", f"founded {company.name}", 0.95, 0.7)
        event = ctx.emit(
            Topics.COMPANY_FOUNDED,
            "founded_company",
            actor=person.person_id,
            target=company_id,
            location=person.district_id,
            payload={"sector": sector.value, "capital_minor": capital, "product": best_code},
            inputs=ImportanceInputs(people_affected=12, economic_impact=capital, political_impact=0.05, novelty=0.8),
        )
        return ActionResult(intent=intent, accepted=True, event_id=event.event_id, outcome={"company_id": company_id})


def _sector_for_product(code: str) -> Sector:
    mapping = {
        "electricity": Sector.ENERGY,
        "water": Sector.WATER,
        "grain": Sector.AGRICULTURE,
        "food": Sector.FOOD,
        "materials": Sector.MANUFACTURING,
        "components": Sector.TECH,
        "electronics": Sector.ELECTRONICS,
        "consumer_goods": Sector.RETAIL,
        "housing": Sector.CONSTRUCTION,
        "transport": Sector.LOGISTICS,
        "services": Sector.SERVICES,
        "healthcare": Sector.HEALTHCARE,
        "education": Sector.EDUCATION,
        "fuel": Sector.ENERGY,
    }
    return mapping.get(code, Sector.SERVICES)


HANDLERS = (
    RestHandler(),
    GoToWorkHandler(),
    BuyFoodHandler(),
    BuyItemHandler(),
    LookForJobHandler(),
    ApplyForJobHandler(),
    SocialiseHandler(),
    ReadNewsHandler(),
    PostOnlineHandler(),
    ProtestHandler(),
    FoundCompanyHandler(),
)


def register_actions(pipeline: ActionPipeline) -> ActionPipeline:
    for handler in HANDLERS:
        pipeline.register(handler)
    return pipeline
