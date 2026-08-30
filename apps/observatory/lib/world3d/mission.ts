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
 * Narration is Polish because the jury is; instrument labels stay English because the rest
 * of the Observatory, the API and the ledger are. That split is deliberate and applied
 * everywhere in the mission UI.
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
    "Hydra twierdzi, że jest cywilizacją, która działa sama: ma własny stan, własną pamięć i własną historię, a model językowy jest w niej opcjonalnym dodatkiem, nie silnikiem.",
    "Nie jesteś tu, żeby to podziwiać. Jesteś audytem. Sześć stacji, sześć tez, które ten projekt stawia — na każdej podpinasz się do żywego świata i czytasz dowód prosto z symulacji, która właśnie się kręci.",
    "Jeśli któraś teza nie ma pokrycia, zobaczysz to w liczbach na ekranie. Nic tu nie jest nagrane."
  ],
  epilogueTitle: "RAPORT KOŃCOWY",
  epilogue: [
    "Sześć tez, sześć dowodów odczytanych z działającego świata. Żaden z nich nie pochodzi ze scenariusza — wszystkie pochodzą z tego samego stanu, którym symulacja właśnie liczy kolejny tick.",
    "To jest cała teza projektu: świat, który da się zatrzymać, rozłożyć, odtworzyć co do hasha i rozgałęzić — i który biegnie dalej, kiedy nikt nie patrzy."
  ]
} as const;

export const STATIONS: Station[] = [
  {
    id: "kernel",
    code: "K-0",
    ring: "RING 0 · KERNEL",
    title: "PUNKT KOTWICZNY",
    brief:
      "Lądujesz w Hydrze o poranku. Zanim spojrzysz na miasto, sprawdzasz jego metrykę: cztery liczby, które je jednoznacznie identyfikują. Jeśli świat jest tym, za co się podaje, te cztery liczby wystarczą, żeby odtworzyć go w całości na dowolnej innej maszynie.",
    thesis:
      "STATE(t) + AGENT_DECISIONS(t) + WORLD_RULES + DETERMINISTIC_RANDOMNESS = STATE(t+1). Ten sam seed, ta sama konfiguracja i ta sama wersja jądra dają identyczny świat — co do hasha stanu.",
    proof:
      "PRNG to SplitMix64, a każdy strumień losowy jest wyprowadzany etykietą przez BLAKE2b, więc nic nie zależy od kolejności wywołań. Systemy chodzą w ustalonej kolejności faz. Stan jest kodowany kanonicznie i haszowany co tick. Model językowy jest świadomie wyłączony z hasha konfiguracji — świat ma być odtwarzalny na maszynie bez żadnego providera.",
    falsifier:
      "Gdyby cokolwiek w pętli sięgało po czas systemowy, kolejność słownika albo globalny random, dwa przebiegi z tym samym ziarnem rozjechałyby się na haszu i test determinizmu byłby czerwony.",
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
    title: "JEDNO ZIARNO, CAŁE MIASTO",
    brief:
      "Idziesz ulicą, która ma nazwę, numery i klasę. Nikt jej nie narysował. Wypadła — razem z dzielnicą, kwartałem, działką i budynkiem, w którym ktoś właśnie się budzi — z tego samego ziarna, które przed chwilą przeczytałeś.",
    thesis:
      "Geografia nie jest zasobem projektu. Jest wynikiem: planeta → kontynent → kraj → region → Hydra → dzielnice → kwartały → działki → budynki, wszystko wyprowadzone deterministycznie z jednego mastera.",
    proof:
      "Genesis buduje warstwy w tej kolejności i każdej daje własny strumień losowy. Zoning wylicza gabaryt budynku z jego funkcji i pojemności — mieszkania rosną w górę, fabryki w bok — więc sylwetka miasta jest konsekwencją, a nie dekoracją. To, co widzisz, to projekcja tego stanu, nie osobny model na potrzeby demo.",
    falsifier:
      "Gdyby miasto było przygotowane ręcznie, zmiana ziarna zostawiłaby ten sam układ ulic. Zmienia cały — łącznie z liczbą dzielnic i przebiegiem arterii.",
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
    title: "SEN JEST DARMOWY",
    brief:
      "Nocna dzielnica. Prawie każda kropka jest zimna — ci ludzie śpią. Pytanie, które zadaje audyt, brzmi: ile kosztuje ta noc? W większości symulacji śpiący agent kosztuje tyle samo, co obudzony, bo i tak trzeba go przetworzyć.",
    thesis:
      "SLEEP to pominięcie, nie pętla. Śpiący agent dostaje zero wywołań mózgu i zero wywołań modelu, a po przebudzeniu jedno zbiorcze rozliczenie i streszczenie zmian świata.",
    proof:
      "Przy SLEEP_START system dormancji wylicza tick pobudki i rejestruje agenta jako pominiętego — jądro w ogóle go nie tyka. Populacja jest hybrydowa: Tier A pamięta i decyduje, Tier B jest lekki, Tier C to kohorty liczone statystycznie, z awansem między poziomami. Dlatego 50 000 mieszkańców mieści się w jednym procesie.",
    falsifier:
      "Gdyby sen był pętlą, liczba decyzji na tick nie spadałaby w nocy. Spada — i to jest ta sama liczba, którą widzisz obok.",
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
    title: "PIENIĄDZ SIĘ NIE MNOŻY",
    brief:
      "Hala przemysłowa przy elektrowni. Firma, która tu stoi, ma koszt energii, marżę i konto — i jeśli prąd zdrożeje, nie dostanie o tym powiadomienia z fabuły. Zobaczy to na rachunku i sama zdecyduje, kogo zwolnić.",
    thesis:
      "Gospodarka jest domknięta. Pieniądz to liczby całkowite w groszach, doba przesuwa miliony między kontami i nie tworzy ani jednego grosza z niczego.",
    proof:
      "Nigdzie w kodzie nie ma pieniądza zmiennoprzecinkowego. Ceny wychodzą z kosztów przez graf BOM, firmy mają zapasy, kredyt i bankructwo, a rynek pracy i rynek dóbr rozliczają się w osobnych fazach ticku. Łańcuch prąd → koszt → cena → cięcie produkcji → zwolnienia → nagłówki → polityka nie jest nigdzie zapisany jako scenariusz: każde ogniwo to osobny system, który reaguje na stan.",
    falsifier:
      "Test ekonomii sumuje wszystkie konta przed dobą i po niej. Każda różnica to błąd, nie zaokrąglenie.",
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
    title: "WIEDZA JEST SUBIEKTYWNA",
    brief:
      "Redakcja. Ta sama awaria, cztery różne pierwsze strony — bo każda redakcja ma właściciela, nastawienie i model biznesowy, a jej dziennikarze wiedzą tylko tyle, ile do nich dotarło.",
    thesis:
      "Agent nigdy nie dostaje stanu świata. Dostaje widok zbudowany z własnej wiedzy — i nie może opublikować faktu, którego nie zna.",
    proof:
      "System percepcji buduje AgentView z osobistej wiedzy agenta: fakt, źródło, pewność i szansa na zniekształcenie. Obiekt widoku nie trzyma żadnego uchwytu do świata, więc nie da się go obejść. Informacja rozchodzi się przez media, rozmowę i HydraNet w czasie — plotka wyprzedza sprostowanie.",
    falsifier:
      "Panel obok rozdziela obecność na observed i derived. To, czego widok nie wie na pewno, jest oznaczone jako wywnioskowane i rysowane inaczej — również w tej scenie.",
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
    title: "PRZESZŁOŚĆ JEST NIEZMIENNA",
    brief:
      "Archiwum. Ostatnia stacja i jedyna, która nie mówi o teraźniejszości. Każde zdarzenie w tym mieście zna swoją przyczynę, bo jądro zapisało powiązanie w chwili, w której ono zaszło — nie odtworzyło go później.",
    thesis:
      "Kronika jest tylko dopisywalna, Timeline Zero jest zapieczętowana, a eksperymenty żyją na forkach z własną linią ziaren. Odtworzenie przeszłego stanu jest dokładne, nie przybliżone.",
    proof:
      "Magazyn odrzuca zapis o ticku wcześniejszym niż zapieczętowana głowa. Fork kopiuje snapshot rodzica i wyprowadza swój strumień losowy z derive(parent_seed, 'fork', timeline_id, fork_tick). Replay to najbliższy snapshot plus deterministyczna resymulacja, weryfikowana względem zapisanego hasha kontrolnego — rozjazd jest twardym błędem, nigdy cichym.",
    falsifier:
      "Gdyby historię dało się nadpisać, nie potrzebowałbyś forka, żeby sprawdzić inną politykę. Potrzebujesz — i to jest jedyna droga.",
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
