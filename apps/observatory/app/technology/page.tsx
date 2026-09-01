"use client";

import { Guard, Header, useView } from "@/components/Page";
import { useI18n } from "@/components/I18n";
import { Bar, Stat } from "@/components/Widgets";
import { fmt, Json, money, pct } from "@/lib/api";

export default function TechnologyPage() {
  const { t, term } = useI18n();
  const { data, error, loading } = useView<Json>("/technology", 4000);
  return (
    <>
      <Header title={t("technology.title")} right={data ? t("technology.summary", { count: data.discoveries }) : ""} />
      <Guard loading={loading} error={error} data={data}>
        {data ? (
          <>
            <div className="grid cols-4" style={{ marginBottom: 12 }}>
              <Stat label={t("technology.level")} value={pct(data.tech_level)} />
              <Stat label={t("technology.discoveries")} value={data.discoveries} />
              <Stat label={t("technology.points")} value={fmt(data.research_points, 0)} />
              <Stat label={t("technology.activeProjects")} value={(data.projects as Json[]).filter((p) => p.active).length} />
            </div>
            <div className="grid cols-2">
              <div className="card">
                <h3>{t("technology.graph")}</h3>
                <div className="scroll" style={{ maxHeight: 520 }}>
                  <table>
                    <thead><tr><th>{t("technology.node")}</th><th>{t("technology.field")}</th><th className="num">{t("technology.progress")}</th><th className="num">{t("technology.adoption")}</th><th>{t("common.state")}</th></tr></thead>
                    <tbody>
                      {(data.nodes as Json[]).map((node) => (
                        <tr key={node.id}>
                          <td>{node.name}</td>
                          <td className="muted">{term(node.field)}</td>
                          <td className="num">
                            {node.difficulty ? <Bar value={node.progress} max={node.difficulty} /> : <span className="muted">{t("technology.seed")}</span>}
                          </td>
                          <td className="num">{pct(node.adoption, 0)}</td>
                          <td>{node.unlocked ? <span className="pill on">{t("technology.unlocked")}</span> : <span className="pill">{t("technology.frontier")}</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="card">
                <h3>{t("technology.projects")}</h3>
                <table>
                  <thead><tr><th>{t("technology.project")}</th><th>{t("technology.organisation")}</th><th className="num">{t("technology.researchers")}</th><th className="num">{t("technology.funding")}</th><th>{t("common.state")}</th></tr></thead>
                  <tbody>
                    {(data.projects as Json[]).map((project) => (
                      <tr key={project.id}>
                        <td>{project.tech}</td>
                        <td className="muted">{project.organisation}</td>
                        <td className="num">{project.researchers}</td>
                        <td className="num">{money(project.funding_per_month)}</td>
                        <td>{project.active ? <span className="pill on">{t("technology.running")}</span> : <span className="pill">{t("common.closed")}</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        ) : null}
      </Guard>
    </>
  );
}
