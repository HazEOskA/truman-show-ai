"use client";

import { usePathname } from "next/navigation";

import Nav from "@/components/Nav";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isPlayCity = pathname === "/city/play";
  const isCityStage = pathname === "/city";

  return (
    <div
      className={`shell ${isPlayCity ? "shell--play" : "shell--observatory"} ${
        isCityStage ? "shell--city-stage" : ""
      }`}
    >
      <Nav />
      <main className="main">{children}</main>
    </div>
  );
}
