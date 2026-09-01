"use client";

import Link from "next/link";

import { useI18n } from "@/components/I18n";

const EVENTS = [
  ["02:13:10", "preview.event.grid", "OK"],
  ["02:11:42", "preview.event.forest", "+0.8%"],
  ["02:09:03", "preview.event.company", "LIVE"],
  ["02:06:18", "preview.event.citizen", "OBS"],
];

export default function ObservatoryPreviewPage() {
  const { t } = useI18n();

  return (
    <div className="observatory-preview">
      <section className="preview-hero">
        <div>
          <div className="preview-eyebrow">{t("preview.eyebrow")}</div>
          <h1>{t("preview.title")}</h1>
          <p>{t("preview.subtitle")}</p>
        </div>
        <span className="preview-live-chip"><i />{t("nav.live")}</span>
      </section>

      <section className="preview-kpi-grid" aria-label={t("preview.worldStatus")}>
        <article className="preview-card preview-kpi">
          <span>{t("preview.worldTime")}</span>
          <strong>14:32</strong>
        </article>
        <article className="preview-card preview-kpi">
          <span>{t("preview.tick")}</span>
          <strong>#084921</strong>
        </article>
        <article className="preview-card preview-kpi">
          <span>{t("preview.agents")}</span>
          <strong>4,920</strong>
        </article>
        <article className="preview-card preview-kpi">
          <span>{t("preview.events")}</span>
          <strong>37</strong>
        </article>
      </section>

      <section className="preview-grid">
        <article className="preview-card preview-city-card">
          <header className="preview-card-head">
            <div>
              <span className="preview-section-label">LIVE // CITY</span>
              <strong>{t("preview.city")}</strong>
            </div>
            <div className="preview-card-actions">
              <Link href="/city">{t("preview.openCity")}</Link>
              <button type="button">{t("preview.fullscreen")}</button>
            </div>
          </header>
          <div className="preview-city-stage">
            <div className="preview-city-message">
              <strong>STITCH / HYDRA CITY VIEW</strong>
              <p>{t("preview.cityHint")}</p>
            </div>
          </div>
        </article>

        <div className="preview-side-stack">
          <article className="preview-card">
            <header className="preview-card-head">
              <div>
                <span className="preview-section-label">{t("preview.eventStream")}</span>
                <strong>{t("preview.activity")}</strong>
              </div>
            </header>
            <div className="preview-list">
              {EVENTS.map(([time, eventKey, state]) => (
                <div className="preview-list-row" key={`${time}-${eventKey}`}>
                  <i />
                  <div>
                    <strong>{t(eventKey)}</strong>
                    <small>{time}</small>
                  </div>
                  <b>{state}</b>
                </div>
              ))}
            </div>
          </article>

          <article className="preview-card">
            <header className="preview-card-head">
              <div>
                <span className="preview-section-label">{t("preview.worldSystems")}</span>
                <strong>{t("preview.systems")}</strong>
              </div>
            </header>
            <div className="preview-system-grid">
              <div className="preview-system-tile">
                <span>{t("preview.economy")}</span>
                <strong>97.4%</strong>
                <small>{t("preview.good")}</small>
              </div>
              <div className="preview-system-tile">
                <span>{t("preview.energy")}</span>
                <strong>82.1%</strong>
                <small>{t("preview.good")}</small>
              </div>
              <div className="preview-system-tile">
                <span>{t("preview.resources")}</span>
                <strong>91.8%</strong>
                <small>{t("preview.good")}</small>
              </div>
              <div className="preview-system-tile">
                <span>{t("preview.environment")}</span>
                <strong>88.6%</strong>
                <small>{t("preview.good")}</small>
              </div>
            </div>
          </article>

          <article className="preview-card">
            <header className="preview-card-head">
              <div>
                <span className="preview-section-label">{t("preview.runtimeLabel")}</span>
                <strong>{t("preview.runtime")}</strong>
              </div>
            </header>
            <div className="preview-list">
              {[t("preview.worker"), t("preview.api"), t("preview.database")].map((item) => (
                <div className="preview-list-row" key={item}>
                  <i />
                  <strong>{item}</strong>
                  <b>ONLINE</b>
                </div>
              ))}
            </div>
          </article>
        </div>
      </section>
    </div>
  );
}
