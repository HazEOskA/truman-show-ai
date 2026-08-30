/**
 * MISSION 01 — WAKE THE CITY.
 *
 * The jury's route through the project.
 *
 * A demo that only shows a pretty city proves nothing: anybody can draw one. So the mission
 * is written as an audit. Each station is one of the claims this repository actually makes,
 * placed on a real building in the running world, and arriving at it opens the evidence for
 * that claim read live out of the simulation — not a slide, not a recording, the numbers the
 * kernel is producing while the jury watches.
 *
 * The station order is the architecture's own order: kernel, genesis, agents, economy,
 * information, history. Walking the city end to end is therefore also walking Ring 0 to
 * Ring 4, which is the whole argument in the shape a person can remember.
 *
 * Narration and instrument labels are English-first, matching the Observatory, API and
 * ledger throughout the competition interface.
 */

/**
 * Every figure a station may show.
 *
 * Each one has to resolve against something the running world actually publishes -- the read
 * model's metric names, the projection, or the frame stream. A dossier row that always reads
 * "—" is worse than one fewer row: this screen's whole claim is that the numbers are real,
 * and a dash is what the audience remembers.
 */
export type EvidenceKey =
  | "seed"
  | "kernel_version"
  | "config_hash"
  | "state_hash"
  | "tick"
  | "day"
  | "sim_time"
  | "phase"
  | "timeline_id"
  | "actions_executed"
  | "districts"
  | "buildings"
  | "streets"
  | "projection_hash"
  | "population"
  | "individuals"
  | "persistent_agents"
  | "active_agents"
  | "sleeping_agents"
  | "agent_ticks"
  | "tokens_used"
  | "cohort_population"
  | "companies"
  | "unemployment"
  | "cpi"
  | "energy_price"
  | "wages_paid"
  | "production_units"
  | "observed"
  | "derived"
  | "observed_share"
  | "publications"
  | "facts_known"
  | "info_deliveries"
  | "snapshots";

export interface Evidence {
  key: EvidenceKey;
  label: string;
}

export interface Station {
  id: string;
  /** Short code shown on the pylon and in the HUD, e.g. "K-0". */
  code: string;
  ring: string;
  title: string;
  /** The story beat. Why the agent is standing here. */
  brief: string;
  /** The claim being audited. */
  thesis: string;
  /** How the repository enforces the claim — the mechanism, not the marketing. */
  proof: string;
  /** What would be true if the claim were false. Kept honest on purpose. */
  falsifier: string;
  evidence: Evidence[];
  /** The test that fails if the claim stops holding. */
  test: string;
  /** Where in the Observatory a viewer can go and keep pulling this thread. */
  href: string;
  hrefLabel: string;
  colour: string;
}

export const MISSION = {
  code: "MISSION 01",
  name: "WAKE THE CITY",
  operator: "AGENT OSA",
  /** Read at the briefing screen, before anything moves. */
  prologue: [
    "Hydra claims to be a civilization that operates on its own: it has its own state, memory and history, while a language model is an optional layer rather than the engine.",
    "You are not here to admire it. You are the audit. Six stations test six claims made by this project — at each one, connect to the live world and read evidence directly from the simulation as it runs.",
    "If a claim is unsupported, the numbers on screen will expose it. Nothing here is pre-recorded."
  ],
  epilogueTitle: "FINAL REPORT",
  epilogue: [
    "Six claims, six pieces of evidence read from a running world. None comes from a prepared script — every value comes from the same state the simulation is using to resolve its next tick.",
    "That is the project's complete thesis: a world that can be paused, inspected, replayed down to the hash and forked — and that keeps running when nobody is watching."
  ]
} as const;

export const STATIONS: Station[] = [
  {
    id: "kernel",
    code: "K-0",
    ring: "RING 0 · KERNEL",
    title: "ANCHOR POINT",
    brief:
      "You enter Hydra in the morning. Before looking at the city, inspect its identity: four values that uniquely describe it. If the world is what it claims to be, those values are enough to reproduce it completely on another machine.",
    thesis:
      "STATE(t) + AGENT_DECISIONS(t) + WORLD_RULES + DETERMINISTIC_RANDOMNESS = STATE(t+1). The same seed, configuration and kernel version produce an identical world — down to the state hash.",
    proof:
      "The PRNG is SplitMix64 and every random stream is label-derived through BLAKE2b, so nothing depends on call order. Systems execute in a fixed phase order. State is encoded canonically and hashed every tick. The language model is deliberately excluded from the configuration hash so the world can be reproduced without any provider.",
    falsifier:
      "If anything in the loop reached for system time, dictionary ordering or global randomness, two runs with the same seed would diverge at the hash and the determinism test would fail.",
    evidence: [
      { key: "seed", label: "SEED" },
      { key: "kernel_version", label: "KERNEL" },
      { key: "config_hash", label: "CONFIG HASH" },
      { key: "state_hash", label: "STATE HASH" },
      { key: "tick", label: "TICK" },
      { key: "actions_executed", label: "ACTIONS EXECUTED" }
    ],
    test: "tests/test_determinism.py",
    href: "/",
    hrefLabel: "World · identity",
    colour: "#39e6ff"
  },
  {
    id: "genesis",
    code: "G-3",
    ring: "RING 3 · GENESIS",
    title: "ONE SEED, THE WHOLE CITY",
    brief:
      "You walk a street with a name, numbers and a class. Nobody drew it. Together with the district, block, parcel and the building where somebody is waking, it emerged from the same seed you just inspected.",
    thesis:
      "Geography is not a project asset. It is an output: planet → continent → country → region → Hydra → districts → blocks → parcels → buildings, all deterministically derived from one master seed.",
    proof:
      "Genesis builds the layers in that order and assigns each its own random stream. Zoning derives building volume from use and capacity — apartments grow upward, factories outward — so the skyline is a consequence rather than decoration. What you see is a projection of state, not a separate model made for the demo.",
    falsifier:
      "If the city were authored by hand, changing the seed would leave the street plan intact. It changes the entire plan, including district count and arterial routes.",
    evidence: [
      { key: "districts", label: "DISTRICTS" },
      { key: "buildings", label: "BUILDINGS" },
      { key: "streets", label: "STREET SEGMENTS" },
      { key: "projection_hash", label: "PROJECTION HASH" },
      { key: "population", label: "POPULATION" }
    ],
    test: "tests/test_scenario.py",
    href: "/city",
    hrefLabel: "City View · plan",
    colour: "#3cffd4"
  },
  {
    id: "agents",
    code: "A-2",
    ring: "RING 2 · AGENTS · DORMANCY",
    title: "SLEEP IS FREE",
    brief:
      "A district at night. Almost every dot is cold: those people are asleep. The audit asks what that night costs. In most simulations, a sleeping agent costs as much as an awake one because it still has to be processed.",
    thesis:
      "SLEEP is a skip, not a loop. A sleeping agent receives zero brain calls and zero model calls, then one aggregate settlement and world-change summary upon waking.",
    proof:
      "At SLEEP_START the dormancy system computes a wake tick and registers the agent as skipped; the kernel does not touch it. Population is hybrid: Tier A remembers and decides, Tier B is lightweight, Tier C is statistically simulated cohorts with promotion between tiers. That is how 50,000 residents fit in one process.",
    falsifier:
      "If sleep were a loop, decisions per tick would not fall at night. They do — and the live number beside this claim shows it.",
    evidence: [
      { key: "individuals", label: "SIMULATED INDIVIDUALLY" },
      { key: "persistent_agents", label: "TIER A · PERSISTENT" },
      { key: "cohort_population", label: "TIER C · COHORTS" },
      { key: "active_agents", label: "AWAKE NOW" },
      { key: "sleeping_agents", label: "ASLEEP NOW" },
      { key: "agent_ticks", label: "DECISIONS / TICK" },
      { key: "tokens_used", label: "LLM TOKENS USED" }
    ],
    test: "tests/test_sleep.py",
    href: "/people",
    hrefLabel: "People · tiers",
    colour: "#d18bff"
  },
  {
    id: "economy",
    code: "E-2",
    ring: "RING 2 · ECONOMY · COMPANIES",
    title: "MONEY DOES NOT MULTIPLY",
    brief:
      "An industrial hall beside the power plant. The company here has an energy cost, a margin and an account. If power becomes more expensive it receives no narrative cue; it sees the bill and decides what to cut.",
    thesis:
      "The economy is closed. Money is stored as integer minor units; a day moves millions between accounts without creating a single unit from nothing.",
    proof:
      "There is no floating-point money in the code. Prices derive from costs through the BOM graph; companies have inventory, credit and bankruptcy, while labor and goods markets settle in separate tick phases. The power → cost → price → production cuts → layoffs → headlines → policy chain is not scripted: every link is an independent system responding to state.",
    falsifier:
      "The economy test sums every account before and after a day. Any difference is an error, not rounding.",
    evidence: [
      { key: "companies", label: "COMPANIES" },
      { key: "unemployment", label: "UNEMPLOYMENT" },
      { key: "cpi", label: "CPI" },
      { key: "energy_price", label: "ENERGY PRICE" },
      { key: "wages_paid", label: "WAGES PAID" },
      { key: "production_units", label: "UNITS PRODUCED" }
    ],
    test: "tests/test_economy.py",
    href: "/economy",
    hrefLabel: "Economy · markets",
    colour: "#ffe14d"
  },
  {
    id: "information",
    code: "I-2",
    ring: "RING 2 · INFORMATION · MEDIA",
    title: "KNOWLEDGE IS SUBJECTIVE",
    brief:
      "A newsroom. The same failure becomes four different front pages because every outlet has an owner, orientation and business model, while its journalists know only what reached them.",
    thesis:
      "An agent never receives world state. It receives a view built from personal knowledge and cannot publish a fact it does not know.",
    proof:
      "The perception system builds AgentView from the agent's own knowledge: fact, source, certainty and distortion probability. The view object holds no reference to the world, so it cannot bypass that boundary. Information moves through media, conversation and HydraNet over time; rumor can outrun correction.",
    falsifier:
      "The live panel separates observed from derived presence. What the view does not know directly is marked as inferred and rendered differently in this scene as well.",
    evidence: [
      { key: "observed", label: "OBSERVED" },
      { key: "derived", label: "DERIVED" },
      { key: "observed_share", label: "OBSERVED SHARE" },
      { key: "facts_known", label: "FACTS KNOWN" },
      { key: "info_deliveries", label: "INFO DELIVERIES" },
      { key: "publications", label: "PUBLICATIONS" }
    ],
    test: "tests/test_agents.py",
    href: "/media",
    hrefLabel: "Media · narratives",
    colour: "#ff7ac4"
  },
  {
    id: "history",
    code: "H-4",
    ring: "RING 0 · HISTORY · TIMELINES",
    title: "THE PAST IS IMMUTABLE",
    brief:
      "The archive. The last station is the only one not about the present. Every event in this city knows its cause because the kernel recorded the link when it happened rather than reconstructing it later.",
    thesis:
      "The chronicle is append-only, Timeline Zero is sealed, and experiments live on forks with their own seed lineage. Replaying a past state is exact, not approximate.",
    proof:
      "Storage rejects any write earlier than the sealed head. A fork copies its parent's snapshot and derives a random stream with derive(parent_seed, 'fork', timeline_id, fork_tick). Replay uses the nearest snapshot plus deterministic resimulation and verifies it against the stored checksum; divergence is a hard error, never a silent one.",
    falsifier:
      "If history could be overwritten, testing another policy would not require a fork. It does — and that is the only path.",
    evidence: [
      { key: "timeline_id", label: "TIMELINE" },
      { key: "phase", label: "PHASE" },
      { key: "snapshots", label: "SNAPSHOTS" },
      { key: "day", label: "SIMULATED DAYS" },
      { key: "sim_time", label: "SIM TIME" },
      { key: "actions_executed", label: "ACTIONS IN LEDGER" }
    ],
    test: "tests/test_timelines.py · tests/test_persistence.py",
    href: "/timeline",
    hrefLabel: "Timeline · forks",
    colour: "#8fe36b"
  }
];
