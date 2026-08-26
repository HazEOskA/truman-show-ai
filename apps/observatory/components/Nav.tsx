"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS: [string, string][] = [
  ["/", "World"],
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

export default function Nav() {
  const pathname = usePathname();
  return (
    <nav className="sidebar">
      <div className="brand">
        <h1>Hydra</h1>
        <small>World Observatory</small>
      </div>
      <div className="nav">
        {LINKS.map(([href, label]) => (
          <Link key={href} href={href} className={pathname === href ? "active" : ""}>
            {label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
