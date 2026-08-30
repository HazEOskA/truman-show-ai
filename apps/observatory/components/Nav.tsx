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
  /** Also light up for these path prefixes. */
  owns?: string[];
}

const SECTIONS: Array<{ title: string; items: Item[] }> = [
  {
    title: "Lab",
    items: [
      { href: "/lab", label: "Laboratory" },
      { href: "/city/play", label: "Mission 01" }
    ]
  },
  {
    title: "Watch",
    items: [
      { href: "/", label: "World" },
      { href: "/city", label: "City View" },
      { href: "/map", label: "Map 3D" },
      { href: "/hydra", label: "Hydra" }
    ]
  },
  {
    title: "Read",
    items: [
      { href: "/people", label: "People", owns: ["/people/"] },
      { href: "/companies", label: "Companies" },
      { href: "/economy", label: "Economy" },
      { href: "/government", label: "Governments" },
      { href: "/media", label: "Media" },
      { href: "/technology", label: "Technology" },
      { href: "/culture", label: "Culture" }
    ]
  },
  {
    title: "Explain",
    items: [
      { href: "/events", label: "Events" },
      { href: "/causal", label: "Causal graph" },
      { href: "/timeline", label: "Timeline" }
    ]
  }
];

function isActive(item: Item, pathname: string): boolean {
  if (pathname === item.href) return true;
  return (item.owns ?? []).some((prefix) => pathname.startsWith(prefix));
}

export default function Nav() {
  const pathname = usePathname();
  return (
    <nav className="sidebar">
      <div className="brand">
        <h1>Hydra</h1>
        <small>World Observatory</small>
      </div>
      <div className="nav">
        {SECTIONS.map((section) => (
          <div key={section.title} className="nav-section">
            <span className="nav-title">{section.title}</span>
            {section.items.map((item) => (
              <Link key={item.href} href={item.href} className={isActive(item, pathname) ? "active" : ""}>
                {item.label}
              </Link>
            ))}
          </div>
        ))}
      </div>
    </nav>
  );
}
