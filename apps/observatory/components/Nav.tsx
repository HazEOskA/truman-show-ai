"use client";

/**
 * The Observatory's spine.
 *
 * It used to be fifteen equally-weighted links, which quietly told every first-time visitor
 * that the causal graph and the front door are the same kind of thing. They are not: the
 * Laboratory is where somebody meeting Hydra starts and where the missions are launched, so
 * it leads, and the analytic views group behind it under what they are for.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

interface Item {
  href: string;
  label: string;
  icon: IconName;
  /** Also light up for these path prefixes. */
  owns?: string[];
}

type IconName =
  | "lab"
  | "mission"
  | "world"
  | "city"
  | "map"
  | "hydra"
  | "people"
  | "companies"
  | "economy"
  | "government"
  | "media"
  | "technology"
  | "culture"
  | "events"
  | "causal"
  | "timeline";

const SECTIONS: Array<{ title: string; items: Item[] }> = [
  {
    title: "Lab",
    items: [
      { href: "/lab", label: "Laboratory", icon: "lab" },
      { href: "/city/play", label: "Mission 01", icon: "mission" }
    ]
  },
  {
    title: "Watch",
    items: [
      { href: "/", label: "World", icon: "world" },
      { href: "/city", label: "City View", icon: "city" },
      { href: "/map", label: "Map 3D", icon: "map" },
      { href: "/hydra", label: "Hydra", icon: "hydra" }
    ]
  },
  {
    title: "Read",
    items: [
      { href: "/people", label: "People", icon: "people", owns: ["/people/"] },
      { href: "/companies", label: "Companies", icon: "companies" },
      { href: "/economy", label: "Economy", icon: "economy" },
      { href: "/government", label: "Governments", icon: "government" },
      { href: "/media", label: "Media", icon: "media" },
      { href: "/technology", label: "Technology", icon: "technology" },
      { href: "/culture", label: "Culture", icon: "culture" }
    ]
  },
  {
    title: "Explain",
    items: [
      { href: "/events", label: "Events", icon: "events" },
      { href: "/causal", label: "Causal graph", icon: "causal" },
      { href: "/timeline", label: "Timeline", icon: "timeline" }
    ]
  }
];

function isActive(item: Item, pathname: string): boolean {
  if (pathname === item.href) return true;
  return (item.owns ?? []).some((prefix) => pathname.startsWith(prefix));
}

const ICON_PATHS: Record<IconName, React.ReactNode> = {
  lab: <><path d="M8 3v5l-4 7.2A2.6 2.6 0 0 0 6.3 19h11.4a2.6 2.6 0 0 0 2.3-3.8L16 8V3" /><path d="M7 12h10M7 3h10" /></>,
  mission: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /><path d="M12 2v3m0 14v3M2 12h3m14 0h3" /></>,
  world: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18" /></>,
  city: <><path d="M4 20V8h7v12M11 20V4h9v16M2 20h20" /><path d="M7 11h1m-1 3h1m7-6h1m-1 3h1m-1 3h1" /></>,
  map: <><path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3zM9 3v15m6-12v15" /></>,
  hydra: <><path d="M12 20v-8M12 12C8 12 5 9 5 5m7 7c4 0 7-3 7-7M12 8c-2 0-3-2-3-4m3 4c2 0 3-2 3-4" /><circle cx="5" cy="4" r="1" /><circle cx="19" cy="4" r="1" /></>,
  people: <><circle cx="9" cy="8" r="3" /><circle cx="17" cy="9" r="2" /><path d="M3 20c0-4 2-7 6-7s6 3 6 7m0-5c3 0 5 2 5 5" /></>,
  companies: <><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M8 7V4h8v3M3 12h18M10 12v2h4v-2" /></>,
  economy: <><path d="M4 19V9m5 10V5m5 14v-7m5 7V3" /><path d="M2 21h20" /></>,
  government: <><path d="m3 9 9-6 9 6M5 10v8m5-8v8m4-8v8m5-8v8M3 21h18M2 18h20" /></>,
  media: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m10 9 5 3-5 3zM7 2h10" /></>,
  technology: <><rect x="5" y="5" width="14" height="14" rx="2" /><path d="M9 9h6v6H9zM9 2v3m6-3v3M9 19v3m6-3v3M2 9h3m-3 6h3m14-6h3m-3 6h3" /></>,
  culture: <><path d="M8 3v12a3 3 0 1 1-2-2.8M18 2v11a3 3 0 1 1-2-2.8" /><path d="M8 6l10-2" /></>,
  events: <><path d="M5 3h14v18H5zM8 8h8M8 12h8M8 16h5" /><path d="M3 6h2m-2 4h2m-2 4h2m-2 4h2" /></>,
  causal: <><circle cx="5" cy="12" r="2" /><circle cx="19" cy="6" r="2" /><circle cx="19" cy="18" r="2" /><path d="M7 12h4c3 0 3-6 6-6M11 12c3 0 3 6 6 6" /></>,
  timeline: <><path d="M4 6h7m2 0h7M4 12h11m2 0h3M4 18h4m2 0h10" /><circle cx="12" cy="6" r="1" /><circle cx="16" cy="12" r="1" /><circle cx="9" cy="18" r="1" /></>
};

function NavIcon({ name }: { name: IconName }) {
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      {ICON_PATHS[name]}
    </svg>
  );
}

export default function Nav() {
  const pathname = usePathname();
  return (
    <nav className="sidebar">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">H</span>
        <span className="brand-copy"><h1>Hydra</h1><small>World Observatory</small></span>
      </div>
      <div className="nav">
        {SECTIONS.map((section) => (
          <div key={section.title} className="nav-section">
            <span className="nav-title">{section.title}</span>
            {section.items.map((item) => {
              const active = isActive(item, pathname);
              return (
              <Link key={item.href} href={item.href} className={active ? "active" : ""} aria-current={active ? "page" : undefined}>
                <NavIcon name={item.icon} />
                <span>{item.label}</span>
              </Link>
              );
            })}
          </div>
        ))}
      </div>
      <div className="nav-system">
        <span className="nav-system-dot" />
        <span><b>Deterministic core</b><small>Read-first observatory</small></span>
      </div>
    </nav>
  );
}
