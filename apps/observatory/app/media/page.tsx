"use client";

import { Guard, Header, useView } from "@/components/Page";
import { Bar } from "@/components/Widgets";
import { fmt, Json, pct } from "@/lib/api";

export default function MediaPage() {
  const { data, error, loading } = useView<Json>("/media", 2500);
  return (
    <>
      <Header title="Media &amp; HydraNet" right={data ? `${(data.outlets as Json[]).length} outlets` : ""} />
      <Guard loading={loading} error={error} data={data}>
        {data ? (
          <div className="grid cols-2">
            <div className="card">
              <h3>Outlets</h3>
              <table>
                <thead>
                  <tr><th>Outlet</th><th>Kind</th><th className="num">Audience</th><th className="num">Bias (gov)</th>
                    <th className="num">Accuracy</th><th className="num">Reputation</th></tr>
                </thead>
                <tbody>
                  {(data.outlets as Json[]).map((outlet) => (
                    <tr key={outlet.id}>
                      <td>{outlet.name}</td>
                      <td className="muted">{outlet.kind}</td>
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

              <h3 style={{ marginTop: 14 }}>Narratives</h3>
              <table>
                <thead><tr><th>Topic</th><th>Dominant framing</th><th className="num">Momentum</th></tr></thead>
                <tbody>
                  {(data.narratives as Json[]).map((narrative) => (
                    <tr key={narrative.topic}>
                      <td className="muted">{narrative.topic}</td>
                      <td>{narrative.dominant}</td>
                      <td className="num">{fmt(narrative.momentum, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="card">
              <h3>Front page</h3>
              <div className="scroll" style={{ maxHeight: 300 }}>
                <table>
                  <thead><tr><th className="num">Tick</th><th>Outlet</th><th>Headline</th><th>Framing</th></tr></thead>
                  <tbody>
                    {(data.publications as Json[]).map((publication) => (
                      <tr key={publication.id}>
                        <td className="num muted">{publication.tick}</td>
                        <td className="muted">{publication.outlet}</td>
                        <td className={publication.truth === "distorted" ? "warn" : ""}>{publication.headline}</td>
                        <td className="muted">{publication.framing}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <h3 style={{ marginTop: 14 }}>HydraNet</h3>
              <div className="row" style={{ marginBottom: 8 }}>
                {(data.net.trending as [string, number][]).map(([topic, weight]) => (
                  <span key={topic} className="pill">{topic} · {fmt(weight, 0)}</span>
                ))}
              </div>
              <div className="scroll" style={{ maxHeight: 260 }}>
                <table>
                  <thead><tr><th className="num">Tick</th><th>Site</th><th>Author</th><th>Post</th><th className="num">Reach</th></tr></thead>
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
