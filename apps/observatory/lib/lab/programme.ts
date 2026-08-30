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
 * Narration is Polish, because the jury is; instrument labels and identifiers stay English,
 * because the API, the ledger and the rest of the Observatory are.
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
}

export const MISSIONS: LabMission[] = [
  {
    id: "wake",
    code: "MISSION 01",
    name: "WAKE THE CITY",
    kind: "walkthrough",
    duration: "5–7 min",
    summary:
      "Audyt architektury w formie przejścia przez miasto. Sześć stacji, sześć tez — na każdej dowód czytany na żywo z działającej symulacji. Autopilot prowadzi, jury czyta.",
    proves:
      "Że to nie jest scena zbudowana pod demo: jądro, genesis, agenci, gospodarka, informacja i historia to osobne warstwy, a każda ma test, który ją pilnuje.",
    watch: ["kolejność pierścieni: RING 0 → RING 4", "hash stanu i hash konfiguracji", "observed / derived w panelu obecności"],
    href: "/city/play",
    cta: "ODPAL MISJĘ",
    colour: "#39e6ff"
  },
  {
    id: "blackout",
    code: "MISSION 02",
    name: "BLACKOUT",
    kind: "shock",
    duration: "3–5 min",
    summary:
      "Elektrownia traci 40% mocy. Nikt nie mówi miastu, co ma dalej zrobić — łańcuch układa się sam, ogniwo po ogniwie, w kolejnych fazach ticku.",
    proves:
      "Że łańcuch prąd → koszt → cena → cięcie produkcji → zwolnienia → nagłówki → nastroje → polityka nie jest nigdzie zapisany jako skrypt. Zepsuj jeden generator, a reszta i tak się wydarzy.",
    watch: ["cena energii i CPI", "gotówka i zatrudnienie w firmach", "pierwsze strony: jedno zdarzenie, kilka narracji", "unrest i poparcie rządu"],
    scenario: { name: "plant_failure", params: { loss: 0.4 } },
    href: "/city",
    cta: "WYWOŁAJ AWARIĘ",
    colour: "#ff7a3d"
  },
  {
    id: "coldsnap",
    code: "MISSION 03",
    name: "COLD SNAP",
    kind: "shock",
    duration: "3–4 min",
    summary:
      "Temperatura spada o 12 stopni. Popyt na ogrzewanie rośnie w każdej dzielnicy z osobna, a sieć rozdziela moc według kosztu krańcowego.",
    proves:
      "Że geografia nie jest tłem. Dzielnice mają własną niezawodność zasilania i własne nastroje, więc ten sam mróz uderza w nie różnie.",
    watch: ["moc vs. zapotrzebowanie", "niezawodność zasilania per dzielnica", "warstwa unrest na mapie"],
    scenario: { name: "cold_snap", params: { drop_c: 12 } },
    href: "/map",
    cta: "ZRZUĆ TEMPERATURĘ",
    colour: "#5fb4ff"
  },
  {
    id: "supply",
    code: "MISSION 04",
    name: "SUPPLY SHOCK",
    kind: "shock",
    duration: "3–4 min",
    summary:
      "Z rynku znika połowa surowca. Ceny idą w górę nie dlatego, że ktoś je podniósł, tylko dlatego, że wychodzą z kosztów przez graf materiałowy.",
    proves:
      "Że gospodarka liczy się od dołu: BOM, zapasy, marża, kredyt, bankructwo. Pieniądz jest całkowity i zachowany.",
    watch: ["ceny w rozbiciu na dobra", "zapasy i marże firm", "import i eksport"],
    scenario: { name: "supply_shock", params: { code: "materials", loss: 0.5 } },
    href: "/economy",
    cta: "ODETNIJ DOSTAWY",
    colour: "#ffd24d"
  },
  {
    id: "repair",
    code: "MISSION 05",
    name: "RECOVERY",
    kind: "shock",
    duration: "2–3 min",
    summary:
      "Elektrownia wraca do pracy. Miasto nie wraca do punktu wyjścia — zwolnieni ludzie nie odzyskują pracy w tej samej chwili, a to, w co uwierzyli, zostaje w ich pamięci.",
    proves:
      "Że skutki są trwałe, a nie odwracalne przełącznikiem. Pamięć i wiedza agentów przeżywają zdarzenie, które je wytworzyło.",
    watch: ["bezrobocie po naprawie", "przekonania agentów w widoku osoby", "kronika zdarzeń i graf przyczynowy"],
    scenario: { name: "plant_repair", params: {} },
    href: "/causal",
    cta: "NAPRAW ELEKTROWNIĘ",
    colour: "#6ad19a"
  },
  {
    id: "fork",
    code: "MISSION 06",
    name: "CONTROLLED FORK",
    kind: "experiment",
    duration: "4–6 min",
    summary:
      "Rozgałęź oś czasu i puść dwa warianty tego samego świata obok siebie. Timeline Zero zostaje nietknięta — eksperyment żyje na forku z własną linią ziaren.",
    proves:
      "Że da się prowadzić kontrolowany eksperyment na cywilizacji: ta sama przeszłość, jedna zmieniona decyzja, dwa mierzalne wyniki.",
    watch: ["drzewo osi czasu i fork_tick", "hash stanu w obu gałęziach", "rozjazd metryk po rozgałęzieniu"],
    href: "/timeline",
    cta: "OTWÓRZ OŚ CZASU",
    colour: "#b489ff"
  }
];

/**
 * The claims this repository stakes, and the test that fails when one stops being true.
 *
 * Kept in the jury's language and deliberately falsifiable: each is a sentence somebody
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
    claim: "Ten sam seed daje ten sam świat.",
    mechanism:
      "Seed + wersja jądra + hash konfiguracji identyfikują świat w całości. Stan jest kodowany kanonicznie i haszowany co tick.",
    test: "tests/test_determinism.py"
  },
  {
    id: "sleep",
    claim: "Sen jest darmowy.",
    mechanism:
      "Śpiący agent dostaje zero wywołań mózgu i zero wywołań modelu; po przebudzeniu jedno zbiorcze rozliczenie i streszczenie zmian.",
    test: "tests/test_sleep.py"
  },
  {
    id: "chain",
    claim: "Łańcuch skutków nie jest skryptem.",
    mechanism:
      "Awaria generatora wywołuje wzrost cen, cięcia, zwolnienia, nagłówki i reakcję polityki przez osobne systemy, z których żaden nie zna następnego.",
    test: "tests/test_scenario.py"
  },
  {
    id: "money",
    claim: "Pieniądz jest zachowany.",
    mechanism:
      "Doba przesuwa miliony między kontami i nie tworzy ani jednego grosza. Wszystko w liczbach całkowitych, nigdzie float.",
    test: "tests/test_economy.py"
  },
  {
    id: "knowledge",
    claim: "Wiedza jest subiektywna.",
    mechanism:
      "Agent nie może opublikować faktu, którego nie zna, a jego widok świata nie trzyma uchwytu do stanu świata.",
    test: "tests/test_agents.py"
  },
  {
    id: "history",
    claim: "Przeszłość jest niezmienna.",
    mechanism:
      "Zapieczętowana oś czasu odrzuca zapis do własnej historii. Eksperymenty są możliwe wyłącznie na forkach.",
    test: "tests/test_persistence.py · tests/test_timelines.py"
  },
  {
    id: "replay",
    claim: "Odtworzenie jest dokładne.",
    mechanism:
      "Najbliższy snapshot plus deterministyczna resymulacja odtwarzają świat, weryfikowane względem zapisanych hashy kontrolnych.",
    test: "tests/test_timelines.py"
  }
];

/** The instrument panel: every analytic view, with the one question it answers. */
export const INSTRUMENTS: Array<[href: string, label: string, question: string]> = [
  ["/", "World", "Co się dzieje w tej chwili i ile to kosztuje?"],
  ["/city", "City View", "Gdzie dokładnie jest każdy budynek i każdy człowiek?"],
  ["/map", "Map 3D", "Jak rozkłada się bogactwo, niepokój i zasilanie?"],
  ["/hydra", "Hydra", "Jak zbudowane jest samo miasto?"],
  ["/people", "People", "Kto tu mieszka i w co wierzy?"],
  ["/companies", "Companies", "Które firmy zarabiają, a które się przewracają?"],
  ["/economy", "Economy", "Skąd biorą się ceny?"],
  ["/government", "Governments", "Dlaczego zapadła ta decyzja?"],
  ["/media", "Media", "Kto opowiedział to inaczej i dlaczego?"],
  ["/technology", "Technology", "Co miasto właśnie wynajduje?"],
  ["/culture", "Culture", "Czym żyje ulica?"],
  ["/events", "Events", "Co się wydarzyło?"],
  ["/causal", "Causal graph", "Dlaczego się wydarzyło?"],
  ["/timeline", "Timeline", "Co by było, gdyby?"]
];
