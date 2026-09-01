"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type Language = "pl" | "en";

type Dictionary = Record<string, string>;

const PL: Dictionary = {
  "brand.subtitle": "Autonomiczny świat na żywo",
  "nav.command": "Dowodzenie",
  "nav.world": "Świat",
  "nav.civilization": "Cywilizacja",
  "nav.intelligence": "Inteligencja",
  "nav.commandCenter": "Centrum obserwacji",
  "nav.hydraCore": "Rdzeń Hydry",
  "nav.cityView": "Miasto na żywo",
  "nav.playCity": "Wejdź do miasta",
  "nav.spatialMap": "Mapa przestrzenna",
  "nav.people": "Mieszkańcy",
  "nav.companies": "Firmy",
  "nav.economy": "Gospodarka",
  "nav.government": "Władze",
  "nav.media": "Media",
  "nav.technology": "Technologia",
  "nav.culture": "Kultura",
  "nav.events": "Rejestr zdarzeń",
  "nav.causal": "Łańcuch przyczyn",
  "nav.timeline": "Oś czasu",
  "nav.preview": "Preview mobilny",
  "nav.more": "Więcej",
  "nav.systems": "Systemy",
  "nav.lab": "Lab",
  "nav.live": "NA ŻYWO",
  "nav.online": "OBSERVATORIUM ONLINE",
  "nav.worldLink": "POŁĄCZENIE ZE ŚWIATEM",
  "mobile.world": "Świat",
  "mobile.people": "Mieszkańcy",
  "mobile.systems": "Systemy",
  "mobile.lab": "Lab",
  "mobile.more": "Więcej",
  "preview.eyebrow": "HYDRA WORLD // MOBILE CONTROL",
  "preview.title": "Obserwatorium świata",
  "preview.subtitle": "Mobilny pulpit do obserwacji i sterowania żyjącym światem 24/7.",
  "preview.worldStatus": "Status świata",
  "preview.worldTime": "Czas świata",
  "preview.tick": "Tick",
  "preview.agents": "Aktywni mieszkańcy",
  "preview.events": "Zdarzenia",
  "preview.city": "Miasto na żywo",
  "preview.cityHint": "Miejsce pod docelowy widok Stitch / 3D City View. Ten kontener jest już responsywny i gotowy pod embed.",
  "preview.openCity": "Otwórz miasto",
  "preview.fullscreen": "Pełny ekran",
  "preview.activity": "Najważniejsze zdarzenia",
  "preview.systems": "Systemy świata",
  "preview.runtime": "Stan silnika",
  "preview.good": "Stabilny",
  "preview.worker": "Worker",
  "preview.api": "API",
  "preview.database": "Baza danych",
  "preview.economy": "Gospodarka",
  "preview.energy": "Energia",
  "preview.resources": "Zasoby",
  "preview.environment": "Środowisko"
};

const EN: Dictionary = {
  "brand.subtitle": "Live autonomous world",
  "nav.command": "Command",
  "nav.world": "World",
  "nav.civilization": "Civilization",
  "nav.intelligence": "Intelligence",
  "nav.commandCenter": "World Observatory",
  "nav.hydraCore": "Hydra Core",
  "nav.cityView": "Live City",
  "nav.playCity": "Enter City",
  "nav.spatialMap": "Spatial Map",
  "nav.people": "Citizens",
  "nav.companies": "Companies",
  "nav.economy": "Economy",
  "nav.government": "Government",
  "nav.media": "Media",
  "nav.technology": "Technology",
  "nav.culture": "Culture",
  "nav.events": "Event Ledger",
  "nav.causal": "Causal Chain",
  "nav.timeline": "Timeline",
  "nav.preview": "Mobile Preview",
  "nav.more": "More",
  "nav.systems": "Systems",
  "nav.lab": "Lab",
  "nav.live": "LIVE",
  "nav.online": "OBSERVATORY ONLINE",
  "nav.worldLink": "WORLD LINK",
  "mobile.world": "World",
  "mobile.people": "Citizens",
  "mobile.systems": "Systems",
  "mobile.lab": "Lab",
  "mobile.more": "More",
  "preview.eyebrow": "HYDRA WORLD // MOBILE CONTROL",
  "preview.title": "World Observatory",
  "preview.subtitle": "Mobile control surface for observing and operating a persistent world 24/7.",
  "preview.worldStatus": "World status",
  "preview.worldTime": "World time",
  "preview.tick": "Tick",
  "preview.agents": "Active citizens",
  "preview.events": "Events",
  "preview.city": "Live city",
  "preview.cityHint": "Reserved for the final Stitch / 3D City View. This container is already responsive and embed-ready.",
  "preview.openCity": "Open city",
  "preview.fullscreen": "Fullscreen",
  "preview.activity": "Important events",
  "preview.systems": "World systems",
  "preview.runtime": "Runtime health",
  "preview.good": "Stable",
  "preview.worker": "Worker",
  "preview.api": "API",
  "preview.database": "Database",
  "preview.economy": "Economy",
  "preview.energy": "Energy",
  "preview.resources": "Resources",
  "preview.environment": "Environment"
};

type I18nContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>("pl");

  useEffect(() => {
    const saved = window.localStorage.getItem("hydra-language");
    if (saved === "pl" || saved === "en") setLanguageState(saved);
  }, []);

  const setLanguage = (next: Language) => {
    setLanguageState(next);
    window.localStorage.setItem("hydra-language", next);
    document.documentElement.lang = next;
  };

  const value = useMemo<I18nContextValue>(() => {
    const dictionary = language === "pl" ? PL : EN;
    return {
      language,
      setLanguage,
      t: (key: string) => dictionary[key] ?? key
    };
  }, [language]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used inside I18nProvider");
  return context;
}

export function LanguageSwitch({ compact = false }: { compact?: boolean }) {
  const { language, setLanguage } = useI18n();
  return (
    <div className={compact ? "language-switch language-switch--compact" : "language-switch"} aria-label="Language">
      <button type="button" className={language === "pl" ? "is-active" : ""} onClick={() => setLanguage("pl")}>PL</button>
      <span>/</span>
      <button type="button" className={language === "en" ? "is-active" : ""} onClick={() => setLanguage("en")}>EN</button>
    </div>
  );
}
