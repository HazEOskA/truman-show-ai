# HYDRA WORLD

A persistent artificial civilisation, not a game and not a story generator. Hydra is a city
that keeps its own state, and the people in it have memory, partial knowledge and their own
reasons. The economy actually moves money, firms actually run out of it, information actually
travels — through media, conversation and the city's own internet — and history is whatever
the world happens to do.

The world runs on one equation:

```
STATE(t) + AGENT_DECISIONS(t) + WORLD_RULES + DETERMINISTIC_RANDOMNESS = STATE(t+1)
```

A language model is never part of that equation. It is an optional adapter that can propose
an action or write a sentence; **the whole simulation runs to completion with no provider
configured at all**, and the determinism tests require exactly that.

---

## Quick start

Two ways in. Neither needs a database.

### 1. Run a city from the command line

```bash
python scripts/install_dev_paths.py        # makes hydra.* importable (writes one .pth file)
python scripts/run_world.py --seed 20260826 --days 3
```

```
genesis: 5.1s  hash=6f2c…
day   1  unemployment=0.000  cpi=0.934  energy=8  unrest=0.101  approval=0.551
day   2  unemployment=0.000  cpi=0.951  energy=8  unrest=0.099  approval=0.556
day   3  unemployment=0.000  cpi=0.947  energy=8  unrest=0.098  approval=0.560
```

Add a shock and watch the city deal with it:

```bash
python scripts/run_world.py --days 12 --scenario plant_failure --scenario-tick 864
```

### 2. Run the whole stack

```bash
docker compose up
```

* Observatory — <http://localhost:3000>
* API docs — <http://localhost:8000/docs>

In the Observatory: pick a seed → **Genesis** → **Run**. Then walk the views: the map, the
people, a single person's beliefs, the firms, the markets, city hall, the front pages, the
research graph, the ledger, the causal graph, and the timeline where you can fork the world.

---

## What is actually simulated

| Layer | What it does |
|---|---|
| **Kernel** | tick = 10 simulated minutes, deterministic PRNG, phase-ordered systems, action pipeline, snapshots, failure isolation |
| **Genesis** | one master seed → planet, region, Hydra, its districts, buildings, plants, firms, institutions, media, and its people |
| **Geography** | power grid with merit-order dispatch, water, transport, weather, per-district reliability and unrest |
| **Economy** | integer money, bills of materials, cost-based prices, inventories, imports/exports, banks and loans |
| **Companies** | margin, cash, staffing, pricing, output cuts, layoffs, borrowing, investment, bankruptcy |
| **People** | Tier A persistent agents, Tier B lightweight agents, Tier C cohorts, with promotion between them |
| **Dormancy** | ACTIVE / LIGHT_IDLE / SLEEP / DORMANT / OFFSCREEN — sleep is a skip, not a loop |
| **Memory** | working, episodic, semantic and compressed memory, consolidated during sleep |
| **Information** | objective facts vs. what each person believes, with a source, a confidence and a chance of distortion |
| **Media** | outlets with owners, bias and a business model; one event, several narratives |
| **Government** | policy as a consequence of prices, unemployment, unrest, approval and the treasury |
| **Technology** | a research graph that has to be funded and staffed, and that keeps extending |
| **Demography** | birth, ageing, illness, death and migration for individuals and cohorts alike |
| **History** | append-only ledger, importance scoring, and a causal graph that can answer *why* |
| **Timelines** | Timeline Zero is sealed; experiments happen on forks with their own seed lineage |

---

## The rules this repository actually enforces

These are not aspirations; each one is checked by a test.

1. **Determinism.** Same seed + same config + same kernel version ⇒ identical state hash
   (`tests/test_determinism.py`).
2. **Sleep is free.** A sleeping agent gets zero brain evaluations and zero model calls, and
   is handed a delta summary when it wakes (`tests/test_sleep.py`).
3. **The chain is not scripted.** Break one generator and the price rise, the cost squeeze,
   the output cuts, the layoffs, the headlines, the spread of the news and the policy response
   all follow on their own (`tests/test_scenario.py`).
4. **Money is conserved.** A simulated day moves millions between accounts and creates none of
   it (`tests/test_economy.py`).
5. **Knowledge is subjective.** An agent cannot post a fact it does not know, and its view
   object carries no handle on the world (`tests/test_agents.py`).
6. **The past is immutable.** A sealed timeline refuses a write to its own history; forks are
   the only way to run an experiment (`tests/test_persistence.py`, `tests/test_timelines.py`).
7. **A replay is exact.** Nearest snapshot plus deterministic re-simulation reproduces the
   world, verified against recorded checkpoints (`tests/test_timelines.py`).

```bash
python -m pytest tests -q
```

---

## Layout

```
apps/          api (FastAPI) · observatory (Next.js) · simulation-worker
packages/      one directory per subsystem, all sharing the hydra.* namespace
database/      PostgreSQL schema, including the append-only guard on history
docs/          architecture lock, subsystem contracts, repository map
scripts/       run a world, install import paths, dump contracts
tests/         determinism, sleep, the demo scenario, and a suite per subsystem
```

Start with [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — it is the binding description of
how the pieces fit, written before the code and kept true to it.

---

## Configuration

Everything that changes outcomes lives in `WorldConfig` and nowhere else, so
`seed + kernel version + config hash` identifies a world completely.

| Variable | Meaning | Default |
|---|---|---|
| `HYDRA_DATA_DIR` | filesystem store location | `./data` |
| `HYDRA_DATABASE_URL` | use PostgreSQL instead of the filesystem | unset |
| `HYDRA_LIVE_EVERY_TICKS` | how often the worker publishes live state | `6` |
| `ANTHROPIC_API_KEY` | enables the optional LLM adapter | unset |

Enabling a model changes how the most important agents *decide*; it never changes the world's
mechanics, and it is deliberately excluded from the config hash so that a world stays
replayable on a machine with no provider at all.

---

## Status

`v0.1` — Hydra, one city, ~50 000 residents, hybrid population, running economy, sealed
history, forkable timelines and a read-first Observatory. The milestone plan through `v1.0`
is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
