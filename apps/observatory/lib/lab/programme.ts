/**
 * The laboratory's programme: what a visitor can run, and what each run is meant to settle.
 *
 * The Observatory has always been able to *show* Hydra. What it could not do was tell a
 * person who has five minutes what to look at first, or what any of it was supposed to
 * prove. This file is that missing half — the experiment list and the claim list, written
 * down once so the Lab, the mission and the debrief cannot drift apart.
 *
 * Every mission here runs against the world the visitor already has selected. None of them
 * loads a prepared recording, and none of them is a different simulation with nicer numbers:
 * a mission is a scenario queued on the control channel plus a view worth watching while it
 * lands. If the world is paused, the mission says so rather than pretending to run.
 *
 * The competition interface is English-first, matching the API, ledger and Observatory.
 */

export type MissionKind = "walkthrough" | "shock" | "experiment";

export interface LabMission {
  id: string;
  code: string;
  name: string;
  kind: MissionKind;
  /** Roughly how long a jury should expect to spend on it. */
  duration: string;
  /** The story, in one or two sentences. */
  summary: string;
  /** What the run is evidence for. */
  proves: string;
  /** What to keep an eye on while it runs. */
  watch: string[];
  /** Queued on the control channel before the view opens, when the mission is a shock. */
  scenario?: { name: string; params: Record<string, unknown> };
  /** Where the visitor is taken. */
  href: string;
  cta: string;
  colour: string;
  /** Environmental artwork used as the mission card's visual anchor. */
  image: string;
}

export const MISSIONS: LabMission[] = [
  {
    id: "wake",
    code: "MISSION 01",
    name: "WAKE THE CITY",
    kind: "walkthrough",
    duration: "5–7 min",
    summary:
      "An architecture audit as a walk through the city. Six stations, six claims — each one backed by evidence read live from the running simulation. Autopilot drives; the jury reads.",
    proves:
      "This is not a scene built for a demo: kernel, genesis, agents, economy, information and history are independent layers, each guarded by a test.",
    watch: ["ring order: RING 0 → RING 4", "state hash and configuration hash", "observed / derived presence"],
    href: "/city/play",
    cta: "START MISSION",
    colour: "#39e6ff",
    image: "/ChatGPT Image 30 sie 2026, 05_59_03 (1).png"
  },
  {
    id: "blackout",
    code: "MISSION 02",
    name: "BLACKOUT",
    kind: "shock",
    duration: "3–5 min",
    summary:
      "The power plant loses 40% of its output. Nobody tells the city what to do next — the chain assembles itself, link by link, across successive tick phases.",
    proves:
      "The power → cost → price → production cuts → layoffs → headlines → sentiment → policy chain is not scripted anywhere. Break one generator and the rest still emerges.",
    watch: ["energy price and CPI", "company cash and employment", "one event across multiple front pages", "unrest and government approval"],
    scenario: { name: "plant_failure", params: { loss: 0.4 } },
    href: "/city",
    cta: "TRIGGER FAILURE",
    colour: "#ff7a3d",
    image: "/ChatGPT Image 30 sie 2026, 05_59_04 (2).png"
  },
  {
    id: "coldsnap",
    code: "MISSION 03",
    name: "COLD SNAP",
    kind: "shock",
    duration: "3–4 min",
    summary:
      "Temperature falls by 12 degrees. Heating demand rises district by district while the grid allocates power by marginal cost.",
    proves:
      "Geography is not scenery. Districts have their own power reliability and sentiment, so the same cold snap affects them differently.",
    watch: ["supply versus demand", "power reliability by district", "the unrest layer on the map"],
    scenario: { name: "cold_snap", params: { drop_c: 12 } },
    href: "/map",
    cta: "DROP TEMPERATURE",
    colour: "#5fb4ff",
    image: "/ChatGPT Image 30 sie 2026, 05_59_04 (3).png"
  },
  {
    id: "supply",
    code: "MISSION 04",
    name: "SUPPLY SHOCK",
    kind: "shock",
    duration: "3–4 min",
    summary:
      "Half the material supply disappears. Prices rise because they are derived from costs through the bill-of-materials graph — not because a script raised them.",
    proves:
      "The economy resolves bottom-up: BOM, inventory, margin, credit and bankruptcy. Money is integral and conserved.",
    watch: ["prices by good", "company inventory and margins", "imports and exports"],
    scenario: { name: "supply_shock", params: { code: "materials", loss: 0.5 } },
    href: "/economy",
    cta: "CUT SUPPLY",
    colour: "#ffd24d",
    image: "/ChatGPT Image 30 sie 2026, 05_59_04 (4).png"
  },
  {
    id: "repair",
    code: "MISSION 05",
    name: "RECOVERY",
    kind: "shock",
    duration: "2–3 min",
    summary:
      "The plant comes back online. The city does not reset: laid-off people are not rehired instantly, and what agents came to believe remains in memory.",
    proves:
      "Consequences persist instead of reversing with a switch. Agent memory and knowledge outlive the event that produced them.",
    watch: ["unemployment after repair", "agent beliefs in the person view", "event ledger and causal graph"],
    scenario: { name: "plant_repair", params: {} },
    href: "/causal",
    cta: "REPAIR PLANT",
    colour: "#6ad19a",
    image: "/ChatGPT Image 30 sie 2026, 05_59_04 (5).png"
  },
  {
    id: "fork",
    code: "MISSION 06",
    name: "CONTROLLED FORK",
    kind: "experiment",
    duration: "4–6 min",
    summary:
      "Fork the timeline and run two variants of the same world side by side. Timeline Zero remains untouched; the experiment lives on a branch with its own seed lineage.",
    proves:
      "A controlled experiment can be run on a civilization: identical history, one changed decision, two measurable outcomes.",
    watch: ["timeline tree and fork_tick", "state hash on both branches", "metric divergence after the fork"],
    href: "/timeline",
    cta: "OPEN TIMELINE",
    colour: "#b489ff",
    image: "/ChatGPT Image 30 sie 2026, 05_59_04 (6).png"
  }
];

/**
 * The claims this repository stakes, and the test that fails when one stops being true.
 *
 * Deliberately falsifiable: each is a sentence somebody
 * could disprove by running the suite, not a slogan.
 */
export interface Thesis {
  id: string;
  claim: string;
  mechanism: string;
  test: string;
}

export const THESES: Thesis[] = [
  {
    id: "determinism",
    claim: "The same seed produces the same world.",
    mechanism:
      "Seed + kernel version + configuration hash identify the world completely. State is encoded canonically and hashed every tick.",
    test: "tests/test_determinism.py"
  },
  {
    id: "sleep",
    claim: "Sleep is free.",
    mechanism:
      "A sleeping agent receives zero brain calls and zero model calls; waking produces one aggregate settlement and world-change summary.",
    test: "tests/test_sleep.py"
  },
  {
    id: "chain",
    claim: "The consequence chain is not scripted.",
    mechanism:
      "A generator failure causes price rises, cuts, layoffs, headlines and policy response through independent systems that do not know what comes next.",
    test: "tests/test_scenario.py"
  },
  {
    id: "money",
    claim: "Money is conserved.",
    mechanism:
      "A day moves millions between accounts without creating a single minor unit. Everything is integral; money never uses floats.",
    test: "tests/test_economy.py"
  },
  {
    id: "knowledge",
    claim: "Knowledge is subjective.",
    mechanism:
      "An agent cannot publish a fact it does not know, and its world view holds no reference to the world state.",
    test: "tests/test_agents.py"
  },
  {
    id: "history",
    claim: "The past is immutable.",
    mechanism:
      "A sealed timeline rejects writes into its own history. Experiments are possible only on forks.",
    test: "tests/test_persistence.py · tests/test_timelines.py"
  },
  {
    id: "replay",
    claim: "Replay is exact.",
    mechanism:
      "The nearest snapshot plus deterministic resimulation reconstructs the world and verifies it against stored checksums.",
    test: "tests/test_timelines.py"
  }
];

/** The instrument panel: every analytic view, with the one question it answers. */
export const INSTRUMENTS: Array<[href: string, label: string, question: string]> = [
  ["/", "World", "What is happening now, and what does it cost?"],
  ["/city", "City View", "Where is every building and every person?"],
  ["/map", "Map 3D", "How are wealth, unrest and power distributed?"],
  ["/hydra", "Hydra", "How is the city itself constructed?"],
  ["/people", "People", "Who lives here, and what do they believe?"],
  ["/companies", "Companies", "Which firms thrive, and which fail?"],
  ["/economy", "Economy", "Where do prices come from?"],
  ["/government", "Governments", "Why was this decision made?"],
  ["/media", "Media", "Who framed the event differently, and why?"],
  ["/technology", "Technology", "What is the city inventing?"],
  ["/culture", "Culture", "What is moving through the street?"],
  ["/events", "Events", "What happened?"],
  ["/causal", "Causal graph", "Why did it happen?"],
  ["/timeline", "Timeline", "What if it had happened differently?"]
];
