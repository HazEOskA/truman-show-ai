"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { LanguageSwitch, useI18n } from "@/components/I18n";

type NavItem = {
  href: string;
  labelKey: string;
  code: string;
};

const NAV_GROUPS: { labelKey: string; items: NavItem[] }[] = [
  {
    labelKey: "nav.command",
    items: [
      { href: "/", labelKey: "nav.commandCenter", code: "00" },
      { href: "/preview", labelKey: "nav.preview", code: "P0" },
      { href: "/hydra", labelKey: "nav.hydraCore", code: "01" }
    ]
  },
  {
    labelKey: "nav.world",
    items: [
      { href: "/city", labelKey: "nav.cityView", code: "02" },
      { href: "/city/play", labelKey: "nav.playCity", code: "03" },
      { href: "/map", labelKey: "nav.spatialMap", code: "04" }
    ]
  },
  {
    labelKey: "nav.civilization",
    items: [
      { href: "/people", labelKey: "nav.people", code: "05" },
      { href: "/companies", labelKey: "nav.companies", code: "06" },
      { href: "/economy", labelKey: "nav.economy", code: "07" },
      { href: "/government", labelKey: "nav.government", code: "08" }
    ]
  },
  {
    labelKey: "nav.intelligence",
    items: [
      { href: "/media", labelKey: "nav.media", code: "09" },
      { href: "/technology", labelKey: "nav.technology", code: "10" },
      { href: "/culture", labelKey: "nav.culture", code: "11" },
      { href: "/events", labelKey: "nav.events", code: "12" },
      { href: "/causal", labelKey: "nav.causal", code: "13" },
      { href: "/timeline", labelKey: "nav.timeline", code: "14" }
    ]
  }
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

function DesktopNav({ pathname }: { pathname: string }) {
  const { t } = useI18n();

  return (
    <nav className="sidebar sidebar--command desktop-observatory-nav" aria-label="Hydra navigation">
      <div className="brand brand--command">
        <Link href="/" className="brand-lockup" aria-label="Hydra World Observatory">
          <span className="brand-symbol"><HydraMark /></span>
          <span className="brand-copy">
            <strong>HYDRA WORLD</strong>
            <small>{t("brand.subtitle")}</small>
          </span>
        </Link>
        <div className="desktop-language-row"><LanguageSwitch compact /></div>
      </div>

      <div className="nav-command-scroll">
        {NAV_GROUPS.map((group) => (
          <div className="nav-group" key={group.labelKey}>
            <div className="nav-group-label">{t(group.labelKey)}</div>
            <div className="nav nav--command-list">
              {group.items.map((item) => (
                <Link key={item.href} href={item.href} className={isActive(pathname, item.href) ? "active" : ""}>
                  <span className="nav-code">{item.code}</span>
                  <span>{t(item.labelKey)}</span>
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
          <strong>{t("nav.worldLink")}</strong>
          <small>{t("nav.online")}</small>
        </span>
        <b>{t("nav.live")}</b>
      </div>
    </nav>
  );
}

function MobileNavigation({ pathname }: { pathname: string }) {
  const { t } = useI18n();
  const [moreOpen, setMoreOpen] = useState(false);

  const bottomItems = [
    { href: "/", label: t("mobile.world"), icon: "◈" },
    { href: "/people", label: t("mobile.people"), icon: "◎" },
    { href: "/hydra", label: t("mobile.systems"), icon: "⌁" },
    { href: "/causal", label: t("mobile.lab"), icon: "◇" }
  ];

  return (
    <>
      <header className="mobile-observatory-topbar">
        <Link href="/" className="mobile-brand" aria-label="Hydra World Observatory">
          <span className="mobile-brand-mark"><HydraMark /></span>
          <span>
            <strong>HYDRA</strong>
            <small>WORLD OBSERVATORY</small>
          </span>
        </Link>
        <div className="mobile-topbar-actions">
          <span className="mobile-live"><i />{t("nav.live")}</span>
          <LanguageSwitch compact />
        </div>
      </header>

      <nav className="mobile-bottom-nav" aria-label="Mobile Hydra navigation">
        {bottomItems.map((item) => (
          <Link key={item.href} href={item.href} className={isActive(pathname, item.href) ? "active" : ""}>
            <span className="mobile-nav-icon" aria-hidden="true">{item.icon}</span>
            <span>{item.label}</span>
          </Link>
        ))}
        <button type="button" className={moreOpen ? "active" : ""} onClick={() => setMoreOpen((value) => !value)} aria-expanded={moreOpen}>
          <span className="mobile-nav-icon" aria-hidden="true">•••</span>
          <span>{t("mobile.more")}</span>
        </button>
      </nav>

      {moreOpen ? (
        <div className="mobile-more-backdrop" onClick={() => setMoreOpen(false)}>
          <section className="mobile-more-sheet" onClick={(event) => event.stopPropagation()} aria-label={t("nav.more")}>
            <div className="mobile-sheet-handle" />
            <div className="mobile-sheet-title">{t("nav.more")}</div>
            <div className="mobile-sheet-grid">
              {[
                ["/city", "nav.cityView", "▦"],
                ["/city/play", "nav.playCity", "▶"],
                ["/map", "nav.spatialMap", "⌖"],
                ["/events", "nav.events", "≋"],
                ["/timeline", "nav.timeline", "↦"],
                ["/economy", "nav.economy", "⌁"],
                ["/companies", "nav.companies", "▤"],
                ["/preview", "nav.preview", "▣"]
              ].map(([href, labelKey, icon]) => (
                <Link key={href} href={href} onClick={() => setMoreOpen(false)}>
                  <span aria-hidden="true">{icon}</span>
                  <strong>{t(labelKey)}</strong>
                </Link>
              ))}
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}

export default function Nav() {
  const pathname = usePathname();

  return (
    <>
      <DesktopNav pathname={pathname} />
      <MobileNavigation pathname={pathname} />
    </>
  );
}
