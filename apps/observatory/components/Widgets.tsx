"use client";

import { fmt } from "@/lib/api";

export function Stat({
  label,
  value,
  hint,
  tone
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "good" | "bad" | "warn";
}) {
  return (
    <div className="card stat">
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
  if (!points || points.length < 2) {
    return <div className="muted">no history yet</div>;
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
    <svg width={width} height={height} role="img" aria-label="trend">
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
