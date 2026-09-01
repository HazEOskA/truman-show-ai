"use client";

import { fmt } from "@/lib/api";
import { useI18n } from "@/components/I18n";

export function Stat({
  label,
  value,
  hint,
  tone,
  accent = "cyan"
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "good" | "bad" | "warn";
  accent?: "cyan" | "violet" | "magenta" | "amber" | "green" | "blue";
}) {
  return (
    <div className="card stat" data-accent={accent}>
      <span className="stat-signal" aria-hidden="true" />
      <div className="label">{label}</div>
      <div className={`value ${tone ?? ""}`}>{value}</div>
      {hint ? <div className="delta muted">{hint}</div> : null}
    </div>
  );
}

/** A sparkline drawn as an inline SVG — no chart library, no external requests. */
export function Spark({
  points,
  width = 240,
  height = 44,
  colour = "var(--accent)"
}: {
  points: number[];
  width?: number;
  height?: number;
  colour?: string;
}) {
  const { t } = useI18n();
  if (!points || points.length < 2) {
    return <div className="muted">{t("widget.noHistory")}</div>;
  }
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const path = points
    .map((value, index) => {
      const x = index * step;
      const y = height - ((value - min) / span) * (height - 4) - 2;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg className="sparkline" width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={t("a11y.trend")}>
      <path d={`M0,${height - 1} H${width}`} fill="none" stroke="var(--line)" strokeWidth="1" />
      <path d={path} fill="none" stroke={colour} strokeWidth="1.4" />
    </svg>
  );
}

export function Bar({ value, max = 1, tone }: { value: number; max?: number; tone?: string }) {
  const share = Math.max(0, Math.min(1, value / (max || 1)));
  return (
    <div className="bar" title={fmt(value, 3)}>
      <span style={{ width: `${share * 100}%`, background: tone ?? "var(--accent)" }} />
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function ErrorBox({ message }: { message: string }) {
  return <div className="error">{message}</div>;
}
