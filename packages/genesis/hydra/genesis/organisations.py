"""Genesis of companies, government, media, HydraNet and the research graph."""

from __future__ import annotations

from hydra.companies.model import Company, CompaniesState, Sector, Strategy
from hydra.economy.model import EconomyState, OwnerKind
from hydra.geography.model import BuildingKind, GeographyState
from hydra.government.model import (
    GovernmentState,
    Institution,
    InstitutionKind,
    Party,
)
from hydra.information.net import NetState, Site, SiteKind
from hydra.kernel.config import WorldConfig
from hydra.kernel.ids import company_id as make_company_id
from hydra.media.model import BusinessModel, MediaState, Outlet, OutletKind
from hydra.technology.model import ResearchProject, TechField, TechnologyState, TechNode

from .names import company_name, outlet_name, word
from .seeds import SeedTree

# sector -> (share of firms, product code, energy intensity, capacity range, wage band)
SECTOR_PLAN: tuple[tuple[Sector, float, str, float, tuple[int, int], str], ...] = (
    (Sector.ENERGY, 0.022, "electricity", 3.0, (90_000, 260_000), "skilled"),
    (Sector.ENERGY, 0.014, "fuel", 2.4, (20_000, 70_000), "skilled"),
    (Sector.WATER, 0.010, "water", 2.2, (40_000, 90_000), "skilled"),
    (Sector.AGRICULTURE, 0.045, "grain", 1.1, (8_000, 26_000), "unskilled"),
    (Sector.FOOD, 0.060, "food", 1.3, (10_000, 34_000), "unskilled"),
    (Sector.MANUFACTURING, 0.125, "materials", 2.6, (6_000, 22_000), "skilled"),
    (Sector.ELECTRONICS, 0.060, "electronics", 2.1, (1_200, 5_400), "professional"),
    (Sector.CONSTRUCTION, 0.070, "housing", 1.6, (60, 260), "skilled"),
    (Sector.LOGISTICS, 0.065, "transport", 1.5, (9_000, 30_000), "unskilled"),
    (Sector.RETAIL, 0.156, "consumer_goods", 0.9, (2_500, 9_000), "unskilled"),
    (Sector.SERVICES, 0.140, "services", 0.7, (1_800, 7_000), "skilled"),
    (Sector.FINANCE, 0.030, "services", 0.5, (900, 3_200), "professional"),
    (Sector.HEALTHCARE, 0.045, "healthcare", 1.0, (900, 3_600), "professional"),
    (Sector.EDUCATION, 0.038, "education", 0.8, (700, 2_800), "professional"),
    (Sector.MEDIA, 0.040, "services", 0.6, (500, 2_100), "professional"),
    (Sector.TECH, 0.080, "components", 1.4, (1_400, 6_200), "professional"),
)

WAGE_BANDS = {
    "unskilled": (185_000, 265_000),
    "skilled": (280_000, 420_000),
    "professional": (430_000, 720_000),
}

SECTOR_BUILDINGS: dict[Sector, tuple[BuildingKind, ...]] = {
    Sector.ENERGY: (BuildingKind.POWER_PLANT,),
    Sector.WATER: (BuildingKind.WATER_PLANT,),
    Sector.AGRICULTURE: (BuildingKind.FACTORY,),
    Sector.FOOD: (BuildingKind.FACTORY,),
    Sector.MANUFACTURING: (BuildingKind.FACTORY,),
    Sector.ELECTRONICS: (BuildingKind.FACTORY, BuildingKind.OFFICE),
    Sector.CONSTRUCTION: (BuildingKind.FACTORY, BuildingKind.OFFICE),
    Sector.LOGISTICS: (BuildingKind.TRANSPORT_HUB, BuildingKind.FACTORY),
    Sector.RETAIL: (BuildingKind.RETAIL,),
    Sector.SERVICES: (BuildingKind.OFFICE, BuildingKind.RETAIL),
    Sector.FINANCE: (BuildingKind.OFFICE,),
    Sector.HEALTHCARE: (BuildingKind.HOSPITAL,),
    Sector.EDUCATION: (BuildingKind.SCHOOL, BuildingKind.UNIVERSITY),
    Sector.MEDIA: (BuildingKind.OFFICE, BuildingKind.CULTURE),
    Sector.TECH: (BuildingKind.OFFICE, BuildingKind.DATA_CENTRE),
}


def assign_plant_operators(geography: GeographyState, companies: CompaniesState) -> None:
    """Give every generating unit an owner.

    A plant with no operator is a fact with no consequences: nobody's books move when it
    trips, so nobody reacts. Ownership is what turns an outage into an economic event.
    """

    operators = sorted(
        (c for c in companies.active() if c.product_code == "electricity"),
        key=lambda c: c.company_id,
    )
    if not operators:
        return
    for index, plant_id in enumerate(sorted(geography.power_plants)):
        plant = geography.power_plants[plant_id]
        operator = operators[index % len(operators)]
        plant.operator_id = operator.company_id
        building = geography.buildings.get(plant.building_id)
        if building is not None:
            building.owner_id = operator.company_id


def _missing_producers(economy: EconomyState, state: CompaniesState) -> list[str]:
    """Goods a city needs but nobody makes. A world that starts with one is not finished."""

    produced = {c.product_code for c in state.companies.values()}
    return sorted(code for code in economy.recipes if code not in produced)


def build_companies(
    seeds: SeedTree,
    config: WorldConfig,
    geography: GeographyState,
    economy: EconomyState,
    daily_demand: dict[str, float] | None = None,
) -> CompaniesState:
    state = CompaniesState()
    district_ids = list(geography.districts)
    target = config.economy.company_count

    for sector, share, product_code, energy_intensity, capacity_range, wage_band in SECTOR_PLAN:
        count = max(1, int(round(target * share)))
        for _ in range(count):
            state.next_company_index += 1
            index = state.next_company_index
            rng = seeds.company(index)
            company_id = make_company_id(index)
            district_id = _pick_district(rng, geography, sector, district_ids)
            building = _pick_building(rng, geography, district_id, SECTOR_BUILDINGS.get(sector, (BuildingKind.OFFICE,)))
            wage_lo, wage_hi = WAGE_BANDS[wage_band]
            capacity = float(rng.randint(*capacity_range))
            price = economy.markets[product_code].price_minor
            account = economy.open_account(company_id, OwnerKind.COMPANY, balance_minor=0, overdraft_minor=0)
            company = Company(
                company_id=company_id,
                name=company_name(rng),
                sector=sector,
                district_id=district_id,
                building_id=building,
                account_id=account.account_id,
                product_code=product_code,
                recipe_code=product_code,
                founded_tick=0,
                capacity_units=capacity,
                utilisation=round(rng.uniform(0.68, 0.94), 4),
                price_minor=int(price * rng.uniform(0.95, 1.09)),
                unit_cost_minor=int(price * rng.uniform(0.66, 0.86)),
                average_wage_minor=int(rng.uniform(wage_lo, wage_hi)),
                technology=round(rng.uniform(0.35, 0.8), 4),
                productivity=round(rng.uniform(0.85, 1.25), 4),
                energy_intensity=round(energy_intensity * rng.uniform(0.85, 1.2), 4),
                reputation=round(rng.uniform(0.3, 0.75), 4),
                strategy=rng.weighted_choice(
                    [Strategy.SURVIVE, Strategy.GROW, Strategy.INVEST, Strategy.MILK, Strategy.COST_CUT],
                    [0.34, 0.26, 0.14, 0.14, 0.12],
                ),
            )
            company.inventory[product_code] = round(capacity * rng.uniform(0.4, 1.8), 3)
            for input_code, qty in economy.recipes[product_code].inputs.items():
                company.input_stock[input_code] = round(capacity * qty * rng.uniform(1.0, 4.0), 3)
            company.headcount_target = max(1, int(capacity / rng.uniform(45.0, 220.0)))
            state.companies[company_id] = company
            state.foundations += 1

    if daily_demand:
        _calibrate_capacity(state, economy, daily_demand)
    missing = _missing_producers(economy, state)
    if missing:
        raise ValueError(f"genesis produced a city with no supplier for: {', '.join(missing)}")
    return state


WAGE_SHARE_OF_VALUE_ADDED = 0.80
WORK_HOURS_PER_DAY = 7.0


def _sustainable_wage_minor(company, economy: EconomyState) -> int:
    """The monthly wage a firm's own productivity can actually carry.

    Paying more than the value a worker adds is not a strategy, it is a countdown. Deriving
    the wage from the bill of materials means every sector starts solvent, and later wage
    differences come from productivity and technology rather than from a table.
    """

    recipe = economy.recipes.get(company.recipe_code)
    market = economy.markets.get(company.product_code)
    if recipe is None or market is None or recipe.labour_hours <= 0.0:
        return company.average_wage_minor
    non_labour = 0.0
    for code, qty in recipe.inputs.items():
        input_market = economy.markets.get(code)
        if input_market is not None:
            non_labour += input_market.price_minor * qty
    non_labour += economy.markets["electricity"].price_minor * recipe.energy_kwh
    non_labour += economy.markets["transport"].price_minor * recipe.logistics
    value_added = max(1.0, market.price_minor - non_labour)
    units_per_worker_day = WORK_HOURS_PER_DAY / recipe.labour_hours
    monthly = value_added * units_per_worker_day * 30.0 * WAGE_SHARE_OF_VALUE_ADDED
    return max(60_000, int(monthly))


OPENING_CASH_DAYS = (35, 130)


def fund_companies(state: CompaniesState, economy: EconomyState, seeds: SeedTree) -> None:
    """Open every firm with one to four months of payroll in the bank.

    Cash has to be measured in something the firm actually spends, otherwise a perfectly
    healthy company starts its life one bad week from insolvency for no reason at all.
    """

    for company_id in sorted(state.companies):
        company = state.companies[company_id]
        rng = seeds.rng("company_cash", company_id)
        daily_wages = max(1, int(company.average_wage_minor / 30.0) * max(1, company.headcount_target))
        days = rng.randint(*OPENING_CASH_DAYS)
        cash = daily_wages * days
        account = economy.accounts[company.account_id]
        account.balance_minor = cash
        account.overdraft_minor = daily_wages * 20
        economy.money_supply_minor += cash


def _calibrate_capacity(state: CompaniesState, economy: EconomyState, daily_demand: dict[str, float]) -> None:
    """Scale installed capacity to the demand the city actually generates.

    Without this the world spends its first simulated weeks discovering that it built ten
    times the factories it needs, and every price collapses to its floor. Sizes stay random
    relative to each other; only the sector total is pinned.
    """

    by_product: dict[str, list] = {}
    for company in state.companies.values():
        by_product.setdefault(company.product_code, []).append(company)

    for product_code, firms in by_product.items():
        target = daily_demand.get(product_code, 0.0)
        if target <= 0.0:
            continue
        effective = sum(f.capacity_units * f.utilisation for f in firms)
        if effective <= 0.0:
            continue
        scale = target * 1.06 / effective
        for firm in firms:
            firm.capacity_units = round(max(1.0, firm.capacity_units * scale), 3)
            firm.inventory[product_code] = round(firm.capacity_units * 1.2, 3)
            recipe = economy.recipes.get(product_code)
            if recipe is not None:
                for input_code, qty in recipe.inputs.items():
                    firm.input_stock[input_code] = round(firm.capacity_units * qty * 2.0, 3)
            firm.headcount_target = max(1, firm.headcount())
            # A firm's pay scale follows what its own workers produce.
            base_wage = _sustainable_wage_minor(firm, economy)
            firm.average_wage_minor = int(base_wage * (0.85 + 0.3 * firm.technology) * firm.productivity)


def _pick_district(rng, geography: GeographyState, sector: Sector, district_ids: list[str]) -> str:
    industrial = ["district_steelgate", "district_old_port", "district_marrow_row"]
    central = ["district_hydra_core", "district_lantern_quarter", "district_kestrel_heights"]
    if sector in (Sector.MANUFACTURING, Sector.ENERGY, Sector.LOGISTICS, Sector.AGRICULTURE, Sector.WATER):
        pool = [d for d in industrial if d in geography.districts] or district_ids
    elif sector in (Sector.FINANCE, Sector.MEDIA, Sector.TECH, Sector.SERVICES):
        pool = [d for d in central if d in geography.districts] or district_ids
    else:
        pool = district_ids
    return rng.choice(pool)


def _pick_building(rng, geography: GeographyState, district_id: str, kinds: tuple[BuildingKind, ...]) -> str:
    district = geography.districts[district_id]
    candidates = [b for b in district.building_ids if geography.buildings[b].kind in kinds]
    if not candidates:
        candidates = [b for b in district.building_ids if geography.buildings[b].kind is not BuildingKind.HOUSING]
    if not candidates:
        candidates = district.building_ids
    return rng.choice(candidates)


def build_government(
    seeds: SeedTree,
    config: WorldConfig,
    economy: EconomyState,
) -> GovernmentState:
    state = GovernmentState()
    rng = seeds.institution("city")
    treasury = economy.open_account("city_treasury", OwnerKind.GOVERNMENT, balance_minor=rng.randint(180_000_000, 420_000_000))
    state.treasury_account_id = treasury.account_id
    state.income_tax_rate = config.economy.income_tax_rate
    state.vat_rate = config.economy.vat_rate
    state.corporate_tax_rate = config.economy.corporate_tax_rate
    state.welfare_per_day_minor = 2_600
    state.approval = round(rng.uniform(0.45, 0.62), 4)

    plan = (
        ("gov_city", "Hydra City Government", InstitutionKind.CITY_GOVERNMENT, 0.34, 420),
        ("gov_council", "Hydra City Council", InstitutionKind.PARLIAMENT, 0.03, 45),
        ("gov_court", "Hydra Court of Justice", InstitutionKind.COURT, 0.05, 120),
        ("gov_police", "Hydra Municipal Police", InstitutionKind.POLICE, 0.16, 780),
        ("gov_tax", "Revenue Office", InstitutionKind.TAX_AUTHORITY, 0.04, 160),
        ("gov_services", "Public Services Directorate", InstitutionKind.PUBLIC_SERVICE, 0.28, 1_450),
        ("gov_regulator", "Utilities Regulator", InstitutionKind.REGULATOR, 0.03, 70),
        ("gov_central_bank", "Valdris Central Bank", InstitutionKind.CENTRAL_BANK, 0.02, 90),
        ("gov_intelligence", "City Intelligence Bureau", InstitutionKind.INTELLIGENCE, 0.05, 110),
    )
    total_budget = rng.randint(900_000_000, 1_400_000_000)
    for institution_id, name, kind, budget_share, staff in plan:
        state.institutions[institution_id] = Institution(
            institution_id=institution_id,
            name=name,
            kind=kind,
            account_id=treasury.account_id,
            budget_minor=int(total_budget * budget_share),
            staff=staff,
            effectiveness=round(rng.uniform(0.5, 0.85), 4),
            integrity=round(rng.uniform(0.45, 0.9), 4),
            parent_id="" if kind is InstitutionKind.CITY_GOVERNMENT else "gov_city",
        )
    state.city_government_id = "gov_city"

    party_plan = (
        ("party_civic", "Civic Union", {"market": 0.2, "authority": 0.4, "welfare": 0.6, "green": 0.4}),
        ("party_industry", "Industrial Front", {"market": 0.8, "authority": 0.5, "welfare": 0.2, "green": 0.1}),
        ("party_commons", "Commons Movement", {"market": -0.4, "authority": 0.2, "welfare": 0.9, "green": 0.7}),
        ("party_order", "Order and Home", {"market": 0.3, "authority": 0.9, "welfare": 0.4, "green": 0.2}),
    )
    shares = [rng.uniform(0.15, 0.4) for _ in party_plan]
    total = sum(shares)
    for (party_id, name, ideology), share in zip(party_plan, shares):
        state.parties[party_id] = Party(
            party_id=party_id,
            name=name,
            ideology=ideology,
            support=round(share / total, 4),
            seats=int(round(45 * share / total)),
        )
    state.ruling_party_id = max(state.parties.values(), key=lambda p: p.support).party_id
    state.parties[state.ruling_party_id].in_power = True
    state.public_wage_minor = int(rng.uniform(280_000, 360_000))
    return state


def assign_public_jobs(government: GovernmentState, agents) -> None:  # noqa: ANN001
    """Distribute institutional headcount across working-age cohorts.

    Public employment is employment: these people draw wages, pay tax and buy food, and the
    labour market has to count them.
    """

    total_staff = sum(i.staff for i in government.institutions.values())
    working = [c for c in agents.cohorts.values() if c.age_band not in ("0_17", "65_plus") and c.size > 0]
    working.sort(key=lambda c: c.cohort_id)
    pool = sum(c.size for c in working)
    if pool <= 0 or total_staff <= 0:
        return
    for cohort in working:
        jobs = int(round(total_staff * cohort.size / pool))
        if jobs > 0:
            government.public_jobs[cohort.cohort_id] = jobs


def build_media_and_net(
    seeds: SeedTree,
    geography: GeographyState,
) -> tuple[MediaState, NetState]:
    media = MediaState()
    net = NetState()

    core_sites = (
        ("site_search", "Hydra Search", SiteKind.SEARCH, 0.92, 0.6),
        ("site_social", "Pulse", SiteKind.SOCIAL, 0.74, 0.35),
        ("site_forum", "The Commons Board", SiteKind.FORUM, 0.38, 0.45),
        ("site_market", "Hydra Exchange", SiteKind.MARKETPLACE, 0.44, 0.55),
        ("site_messaging", "Relay", SiteKind.MESSAGING, 0.66, 0.7),
        ("site_underground", "Deadlight", SiteKind.UNDERGROUND, 0.07, 0.2),
    )
    for site_id, name, kind, reach, trust in core_sites:
        net.sites[site_id] = Site(site_id=site_id, name=name, kind=kind, reach=reach, trust=trust)

    outlet_plan = (
        (OutletKind.NEWSPAPER, BusinessModel.SUBSCRIPTION, 0.15, 0.82, 0.24),
        (OutletKind.BROADCAST, BusinessModel.ADVERTISING, -0.05, 0.75, 0.31),
        (OutletKind.STATE, BusinessModel.STATE_FUNDED, 0.72, 0.68, 0.18),
        (OutletKind.TABLOID, BusinessModel.ADVERTISING, -0.35, 0.45, 0.14),
        (OutletKind.NET_NATIVE, BusinessModel.ADVERTISING, -0.15, 0.6, 0.09),
        (OutletKind.INDEPENDENT, BusinessModel.DONATIONS, -0.55, 0.78, 0.04),
    )
    for index, (kind, model, bias_gov, accuracy, audience) in enumerate(outlet_plan):
        rng = seeds.rng("media", index)
        outlet_id = f"outlet_{index + 1:02d}"
        site_id = f"site_news_{index + 1:02d}"
        net.sites[site_id] = Site(
            site_id=site_id,
            name=outlet_name(rng),
            kind=SiteKind.NEWS,
            owner_id=outlet_id,
            reach=round(audience * rng.uniform(1.6, 2.6), 4),
            trust=round(accuracy * rng.uniform(0.8, 1.05), 4),
        )
        media.outlets[outlet_id] = Outlet(
            outlet_id=outlet_id,
            name=net.sites[site_id].name,
            kind=kind,
            business_model=model,
            bias_government=round(bias_gov + rng.uniform(-0.1, 0.1), 4),
            bias_business=round(rng.uniform(-0.6, 0.6), 4),
            sensationalism=round(rng.uniform(0.15, 0.85), 4),
            accuracy=round(min(0.99, max(0.3, accuracy + rng.uniform(-0.08, 0.08))), 4),
            reputation=round(rng.uniform(0.35, 0.8), 4),
            audience_share=round(audience, 4),
            site_id=site_id,
        )

    for district in geography.districts.values():
        site_id = f"site_forum_{district.district_id}"
        net.sites[site_id] = Site(
            site_id=site_id,
            name=f"{district.name} Board",
            kind=SiteKind.FORUM,
            reach=round(0.04 + district.wealth_index * 0.06, 4),
            trust=0.4,
        )
    return media, net


TECH_SEED_GRAPH: tuple[tuple[str, str, TechField, float, tuple[str, ...], dict[str, float]], ...] = (
    ("tech_grid_basics", "Grid Control", TechField.ENERGY, 0.0, (), {"energy_efficiency": 0.02}),
    ("tech_materials_basics", "Alloy Processing", TechField.MATERIALS, 0.0, (), {"productivity": 0.02}),
    ("tech_computing_basics", "Industrial Computing", TechField.COMPUTING, 0.0, (), {"productivity": 0.03}),
    ("tech_medicine_basics", "Clinical Practice", TechField.MEDICINE, 0.0, (), {"health": 0.02}),
    ("tech_smart_grid", "Adaptive Grid", TechField.ENERGY, 2400.0, ("tech_grid_basics", "tech_computing_basics"), {"energy_efficiency": 0.09}),
    ("tech_storage", "Grid Storage", TechField.ENERGY, 3200.0, ("tech_grid_basics", "tech_materials_basics"), {"energy_reserve": 0.12, "energy_efficiency": 0.05}),
    ("tech_precision_mfg", "Precision Manufacturing", TechField.MATERIALS, 2800.0, ("tech_materials_basics",), {"productivity": 0.08}),
    ("tech_automation", "Process Automation", TechField.COMPUTING, 3600.0, ("tech_computing_basics", "tech_precision_mfg"), {"productivity": 0.12, "labour_demand": -0.06}),
    ("tech_vertical_farm", "Vertical Farming", TechField.AGRICULTURE, 3000.0, ("tech_materials_basics",), {"food_yield": 0.15, "energy_demand": 0.05}),
    ("tech_transit_net", "Integrated Transit", TechField.TRANSPORT, 2600.0, ("tech_computing_basics",), {"transport_capacity": 0.12}),
    ("tech_diagnostics", "Rapid Diagnostics", TechField.MEDICINE, 3400.0, ("tech_medicine_basics", "tech_computing_basics"), {"health": 0.07}),
    ("tech_civic_analytics", "Civic Analytics", TechField.SOCIAL, 2200.0, ("tech_computing_basics",), {"gov_effectiveness": 0.08}),
)


def build_technology(seeds: SeedTree, companies: CompaniesState) -> TechnologyState:
    state = TechnologyState()
    rng = seeds.rng("technology")
    for tech_id, name, field_name, difficulty, prerequisites, effects in TECH_SEED_GRAPH:
        node = TechNode(
            tech_id=tech_id,
            name=name,
            field_name=field_name,
            difficulty=difficulty * rng.uniform(0.85, 1.2) if difficulty else 0.0,
            prerequisites=list(prerequisites),
            effects=dict(effects),
            unlocked=difficulty == 0.0,
            unlocked_tick=0 if difficulty == 0.0 else None,
            adoption=0.85 if difficulty == 0.0 else 0.0,
            frontier=difficulty > 0.0,
        )
        state.nodes[tech_id] = node

    research_capable = [c for c in companies.active() if c.sector.value in ("tech", "electronics", "energy", "healthcare")]
    for index, company in enumerate(research_capable[:8]):
        available = [n for n in state.available() if n.difficulty > 0]
        if not available:
            break
        node = available[index % len(available)]
        state.next_project_index += 1
        state.projects[f"project_{state.next_project_index:04d}"] = ResearchProject(
            project_id=f"project_{state.next_project_index:04d}",
            tech_id=node.tech_id,
            organisation_id=company.company_id,
            researchers=rng.randint(3, 24),
            funding_per_month_minor=rng.randint(200_000, 3_500_000),
            started_tick=0,
            progress_rate=round(rng.uniform(0.7, 1.4), 4),
        )
    state.tech_level = 0.5
    return state
