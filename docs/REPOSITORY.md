# Repository map

```
hydra-world/
│
├── apps/
│   ├── api/                    FastAPI: world lifecycle, control, projections, SSE stream
│   ├── observatory/            Next.js read-first Observatory
│   └── simulation-worker/      the only process that advances time
│
├── packages/                   one directory per subsystem; all share the `hydra.*` namespace
│   ├── world-kernel/           hydra.kernel — clock, PRNG, scheduler, actions, snapshots
│   ├── events/                 hydra.events — event schema, importance, bus
│   ├── genesis/                hydra.genesis — seed tree, world construction, SEAL
│   ├── geography/              hydra.geography — planet → district, grid, water, transport
│   ├── population/             hydra.population — households, consumption, housing
│   ├── agents/                 hydra.agents — tiers, views, brains, actions, LLM adapter
│   ├── dormancy/               hydra.dormancy — sleep/idle/dormant lifecycle
│   ├── memory/                 hydra.memory — layered memory and consolidation
│   ├── social/                 hydra.social — temporal relationship graph
│   ├── economy/                hydra.economy — money, BOM, prices, clearing, banking
│   ├── companies/              hydra.companies — production, payroll, firm decisions
│   ├── government/             hydra.government — institutions, policy, elections, tax
│   ├── information/            hydra.information — facts, subjective knowledge, HydraNet
│   ├── media/                  hydra.media — outlets, framing, narratives
│   ├── technology/             hydra.technology — research graph and adoption
│   ├── demographics/           hydra.demographics — birth, ageing, death, migration
│   ├── culture/                hydra.culture — emergent slang, movements, conspiracies
│   ├── history/                hydra.history — ledger, chronicle, causal graph
│   ├── timelines/              hydra.timelines — replay and forks
│   ├── persistence/            hydra.persistence — store contract, file and Postgres backends
│   └── world/                  hydra.world — composition root and operator scenarios
│
├── database/schema.sql         PostgreSQL schema with the append-only history guard
├── docs/                       architecture lock, contracts, this map
├── scripts/                    run_world.py, install_dev_paths.py, dump_contracts.py
├── tests/                      determinism, sleep, scenario, and a suite per subsystem
├── docker/                     one Dockerfile per app
└── docker-compose.yml          the whole stack for local development
```

## Why one directory per package

Each subsystem is a separate directory contributing to the same PEP 420 namespace
(`hydra.economy`, `hydra.agents`, …). That keeps the dependency direction visible — a package
can only import what it declares — while `python scripts/install_dev_paths.py` writes a single
`.pth` file so the whole namespace imports cleanly from a clone, with no build step.

## Dependency direction

```
apps  →  hydra.world  →  domain packages  →  hydra.events  →  hydra.kernel
```

The kernel imports no domain. Domains import no app. The composition root
(`packages/world/hydra/world/builder.py`) is the only place that knows about all of them, and
it is the only file to change when adding a subsystem.
