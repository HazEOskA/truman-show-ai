"use client";

import { Guard, Header, useView } from "@/components/Page";
import { useI18n } from "@/components/I18n";
import { Bar } from "@/components/Widgets";
import { fmt, Json, pct } from "@/lib/api";

export default function MediaPage() {
  const { t, term } = useI18n();
  const { data, error, loading } = useView<Json>("/media", 2500);
  return (
    <>
      <Header title={t("media.title")} right={data ? t("media.summary", { count: (data.outlets as Json[]).length }) : ""} />
      <Guard loading={loading} error={error} data={data}>
        {data ? (
          <div className="grid cols-2">
            <div className="card">
              <h3>{t("media.outlets")}</h3>
              <table>
                <thead>
                  <tr><th>{t("media.outlet")}</th><th>{t("common.kind")}</th><th className="num">{t("media.audience")}</th><th className="num">{t("media.bias")}</th>
                    <th className="num">{t("media.accuracy")}</th><th className="num">{t("media.reputation")}</th></tr>
                </thead>
                <tbody>
                  {(data.outlets as Json[]).map((outlet) => (
                    <tr key={outlet.id}>
                      <td>{outlet.name}</td>
                      <td className="muted">{term(outlet.kind)}</td>
                      <td className="num">{pct(outlet.audience_share)}</td>
                      <td className={`num ${outlet.bias_government < -0.2 ? "bad" : outlet.bias_government > 0.2 ? "good" : ""}`}>
                        {fmt(outlet.bias_government, 2)}
                      </td>
                      <td className="num">{pct(outlet.accuracy, 0)}</td>
                      <td className="num"><Bar value={outlet.reputation} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <h3 style={{ marginTop: 14 }}>{t("media.narratives")}</h3>
              <table>
                <thead><tr><th>{t("common.topic")}</th><th>{t("media.dominant")}</th><th className="num">{t("media.momentum")}</th></tr></thead>
                <tbody>
                  {(data.narratives as Json[]).map((narrative) => (
                    <tr key={narrative.topic}>
                      <td className="muted">{term(narrative.topic)}</td>
                      <td>{term(narrative.dominant)}</td>
                      <td className="num">{fmt(narrative.momentum, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="card">
              <h3>{t("media.frontPage")}</h3>
              <div className="scroll" style={{ maxHeight: 300 }}>
                <table>
                  <thead><tr><th className="num">{t("common.tick")}</th><th>{t("media.outlet")}</th><th>{t("media.headline")}</th><th>{t("media.framing")}</th></tr></thead>
                  <tbody>
                    {(data.publications as Json[]).map((publication) => (
                      <tr key={publication.id}>
                        <td className="num muted">{publication.tick}</td>
                        <td className="muted">{publication.outlet}</td>
                        <td className={publication.truth === "distorted" ? "warn" : ""}>{publication.headline}</td>
                        <td className="muted">{term(publication.framing)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <h3 style={{ marginTop: 14 }}>HydraNet</h3>
              <div className="row" style={{ marginBottom: 8 }}>
                {(data.net.trending as [string, number][]).map(([topic, weight]) => (
                  <span key={topic} className="pill">{term(topic)} · {fmt(weight, 0)}</span>
                ))}
              </div>
              <div className="scroll" style={{ maxHeight: 260 }}>
                <table>
                  <thead><tr><th className="num">{t("common.tick")}</th><th>{t("media.site")}</th><th>{t("media.author")}</th><th>{t("media.post")}</th><th className="num">{t("media.reach")}</th></tr></thead>
                  <tbody>
                    {(data.net.posts as Json[]).map((post) => (
                      <tr key={post.id}>
                        <td className="num muted">{post.tick}</td>
                        <td className="muted">{post.site}</td>
                        <td className="muted">{post.author}</td>
                        <td>{post.text}</td>
                        <td className="num">{fmt(post.reach, 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        ) : null}
      </Guard>
    </>
  );
}
