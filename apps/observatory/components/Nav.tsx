"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

type NavItem = {
  href: string;
  label: string;
  code: string;
};

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Command",
    items: [
      { href: "/", label: "Command Center", code: "00" },
      { href: "/hydra", label: "Hydra Core", code: "01" }
    ]
  },
  {
    label: "World",
    items: [
      { href: "/city", label: "City View", code: "02" },
      { href: "/city/play", label: "Play City", code: "03" },
      { href: "/map", label: "Spatial Map", code: "04" }
    ]
  },
  {
    label: "Civilization",
    items: [
      { href: "/people", label: "People", code: "05" },
      { href: "/companies", label: "Companies", code: "06" },
      { href: "/economy", label: "Economy", code: "07" },
      { href: "/government", label: "Government", code: "08" }
    ]
  },
  {
    label: "Intelligence",
    items: [
      { href: "/media", label: "Media", code: "09" },
      { href: "/technology", label: "Technology", code: "10" },
      { href: "/culture", label: "Culture", code: "11" },
      { href: "/events", label: "Event Ledger", code: "12" },
      { href: "/causal", label: "Causal Graph", code: "13" },
      { href: "/timeline", label: "Timelines", code: "14" }
    ]
  }
];

const LEGACY_LINKS: [string, string][] = [
  ["/", "World"],
  ["/city", "City View"],
  ["/city/play", "Play City"],
  ["/map", "Map"],
  ["/hydra", "Hydra"],
  ["/people", "People"],
  ["/companies", "Companies"],
  ["/economy", "Economy"],
  ["/government", "Governments"],
  ["/media", "Media"],
  ["/technology", "Technology"],
  ["/culture", "Culture"],
  ["/events", "Events"],
  ["/causal", "Causal graph"],
  ["/timeline", "Timeline"]
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  if (href === "/city") return pathname === "/city" || (pathname.startsWith("/city/") && pathname !== "/city/play");
  return pathname === href || pathname.startsWith(`${href}/`);
}

function HydraMark() {
  return (
    <svg className="hydra-mark" viewBox="0 0 64 64" aria-hidden="true">
      <path d="M13 12 25 19 32 8 39 19 51 12 46 28 55 34 43 39 43 53 32 46 21 53 21 39 9 34 18 28Z" />
      <circle cx="24" cy="30" r="2.2" />
      <circle cx="40" cy="30" r="2.2" />
      <path className="hydra-mark-core" d="m25 38 7 4 7-4-7-5Z" />
    </svg>
  );
}

function LegacyNav({ pathname }: { pathname: string }) {
  return (
    <nav className="sidebar sidebar--legacy" aria-label="Hydra navigation">
      <div className="brand brand--legacy">
        <h1>Hydra</h1>
        <small>World Observatory</small>
      </div>
      <div className="nav nav--legacy">
        {LEGACY_LINKS.map(([href, label]) => (
          <Link key={href} href={href} className={isActive(pathname, href) ? "active" : ""}>
            {label}
          </Link>
        ))}
      </div>
    </nav>
  );
}

export default function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  if (pathname === "/city/play") return <LegacyNav pathname={pathname} />;

  return (
    <nav className={open ? "sidebar sidebar--command is-open" : "sidebar sidebar--command"} aria-label="Hydra navigation">
      <div className="brand brand--command">
        <Link href="/" className="brand-lockup" onClick={() => setOpen(false)} aria-label="Hydra Command Center">
          <span className="brand-symbol"><HydraMark /></span>
          <span className="brand-copy">
            <strong>OSA // HYDRA</strong>
            <small>World Observatory</small>
          </span>
        </Link>
        <button
          type="button"
          className="nav-toggle"
          aria-expanded={open}
          aria-label={open ? "Close navigation" : "Open navigation"}
          onClick={() => setOpen((value) => !value)}
        >
          <span />
          <span />
        </button>
      </div>

      <div className="nav-command-scroll">
        {NAV_GROUPS.map((group) => (
          <div className="nav-group" key={group.label}>
            <div className="nav-group-label">{group.label}</div>
            <div className="nav nav--command-list">
              {group.items.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={isActive(pathname, item.href) ? "active" : ""}
                  onClick={() => setOpen(false)}
                >
                  <span className="nav-code">{item.code}</span>
                  <span>{item.label}</span>
                  <span className="nav-arrow" aria-hidden="true">↗</span>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="sidebar-status">
        <span className="status-orb" aria-hidden="true" />
        <span>
          <strong>WORLD LINK</strong>
          <small>OBSERVATORY ONLINE</small>
        </span>
        <b>LIVE</b>
      </div>
    </nav>
  );
}
