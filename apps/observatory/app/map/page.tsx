"use client";

import { useEffect, useRef, useState } from "react";
import { Guard, Header, useView } from "@/components/Page";
import { useI18n } from "@/components/I18n";
import { fmt, Json, pct } from "@/lib/api";

type Metric = "wealth_index" | "unrest" | "pollution" | "power_reliability" | "population";

const METRICS: [Metric, string][] = [
  ["wealth_index", "map.wealth"],
  ["unrest", "map.unrest"],
  ["pollution", "map.pollution"],
  ["power_reliability", "map.powerReliability"],
  ["population", "map.population"]
];

export default function MapPage() {
  const { t } = useI18n();
  const { data, error, loading } = useView<Json>("/city", 2000);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [metric, setMetric] = useState<Metric>("wealth_index");
  const [hover, setHover] = useState<Json | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    const districts = data.districts as Json[];
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#0a0c10";
    ctx.fillRect(0, 0, width, height);

    const xs = districts.map((d) => d.x as number);
    const ys = districts.map((d) => d.y as number);
    const minX = Math.min(...xs) - 3;
    const maxX = Math.max(...xs) + 3;
    const minY = Math.min(...ys) - 3;
    const maxY = Math.max(...ys) + 3;
    const scaleX = width / (maxX - minX);
    const scaleY = height / (maxY - minY);

    const values = districts.map((d) => Number(d[metric] ?? 0));
    const vMin = Math.min(...values);
    const vMax = Math.max(...values);

    districts.forEach((district) => {
      const value = Number(district[metric] ?? 0);
      const share = (value - vMin) / (vMax - vMin || 1);
      const x = (Number(district.x) - minX) * scaleX;
      const y = (Number(district.y) - minY) * scaleY;
      const radius = 18 + Math.sqrt(Number(district.population)) / 6;

      const gradient = ctx.createRadialGradient(x, y, 2, x, y, radius);
      gradient.addColorStop(0, `rgba(79, 209, 197, ${0.25 + share * 0.65})`);
      gradient.addColorStop(1, "rgba(79, 209, 197, 0.02)");
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fill();

      ctx.strokeStyle = "rgba(122, 162, 247, 0.5)";
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.fillStyle = "#dfe4ee";
      ctx.font = "11px ui-monospace, monospace";
      ctx.fillText(String(district.name), x - radius / 2, y - radius - 5);
      ctx.fillStyle = "#8b93a5";
      ctx.fillText(
        metric === "population" ? fmt(value, 0) : pct(value),
        x - radius / 2,
        y - radius + 8
      );
    });
  }, [data, metric]);

  return (
    <>
      <Header title={t("map.title")} right={data ? t("map.districts", { count: (data.districts as Json[]).length }) : ""} />
      <Guard loading={loading} error={error} data={data}>
        <div className="card">
          <div className="row" style={{ marginBottom: 10 }}>
            {METRICS.map(([key, labelKey]) => (
              <button key={key} className={metric === key ? "primary" : ""} onClick={() => setMetric(key)}>
                {t(labelKey)}
              </button>
            ))}
          </div>
          <canvas
            ref={canvasRef}
            width={900}
            height={520}
            role="img"
            aria-label={t("map.canvas")}
            style={{ width: "100%", maxWidth: 900, border: "1px solid var(--line)", borderRadius: 6 }}
            onMouseLeave={() => setHover(null)}
          />
          {hover ? <div className="muted">{hover.name}</div> : null}
        </div>
      </Guard>
    </>
  );
}
