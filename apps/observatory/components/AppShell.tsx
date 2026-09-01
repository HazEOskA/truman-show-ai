"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";

import { I18nProvider } from "@/components/I18n";
import Nav from "@/components/Nav";

function routeClass(pathname: string): string {
  if (pathname === "/") return "route-home";
  return `route-${pathname.replace(/^\//, "").replace(/\//g, "-")}`;
}

function useMobileDevice(): boolean {
  const [mobile, setMobile] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 900px), (pointer: coarse)");
    const update = () => {
      const touchPhone = navigator.maxTouchPoints > 0 && Math.min(window.screen.width, window.screen.height) <= 900;
      setMobile(media.matches || touchPhone);
    };

    update();
    media.addEventListener?.("change", update);
    window.addEventListener("orientationchange", update);
    window.addEventListener("resize", update);
    return () => {
      media.removeEventListener?.("change", update);
      window.removeEventListener("orientationchange", update);
      window.removeEventListener("resize", update);
    };
  }, []);

  return mobile;
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isPlayCity = pathname === "/city/play";
  const isCityStage = pathname === "/city";
  const mobile = useMobileDevice();
  const currentRouteClass = useMemo(() => routeClass(pathname), [pathname]);

  return (
    <I18nProvider>
      <div
        data-route={pathname}
        data-mobile={mobile ? "true" : "false"}
        className={`shell ${isPlayCity ? "shell--play" : "shell--observatory"} ${
          isCityStage ? "shell--city-stage" : ""
        } ${mobile ? "is-mobile-device" : "is-desktop-device"}`}
      >
        <Nav />
        <main className={`main route-main ${currentRouteClass}`}>{children}</main>
      </div>
    </I18nProvider>
  );
}
