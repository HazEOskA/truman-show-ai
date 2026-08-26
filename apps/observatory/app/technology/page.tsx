"use client";

import { Guard, Header, useView } from "@/components/Page";
import { Bar, Stat } from "@/components/Widgets";
import { fmt, Json, money, pct } from "@/lib/api";

export default function TechnologyPage() {
  const { data, error, loading } = useView<Json>("/technology", 4000);
  return (
    <>
      <Header title="Technology" right={data ? `${data.discoveries} discoveries` : ""} />
      <Guard loading={loading} error={error} data={data}>
        {data ? (
          <>
            <div className="grid cols-4" style={{ marginBottom: 12 }}>
              <Stat label="Tech level" value={pct(data.tech_level)} />
              <Stat label="Discoveries" value={data.discoveries} />
              <Stat label="Research points" value={fmt(data.research_points, 0)} />
              <Stat label="Active projects" value={(data.projects as Json[]).filter((p) => p.active).length} />
            </div>
            <div className="grid cols-2">
              <div className="card">
                <h3>Research graph</h3>
                <div className="scroll" style={{ maxHeight: 520 }}>
                  <table>
                    <thead><tr><th>Node</th><th>Field</th><th className="num">Progress</th><th className="num">Adoption</th><th>State</th></tr></thead>
                    <tbody>
                      {(data.nodes as Json[]).map((node) => (
                        <tr key={node.id}>
                          <td>{node.name}</td>
                          <td className="muted">{node.field}</td>
                          <td className="num">
                            {node.difficulty ? <Bar value={node.progress} max={node.difficulty} /> : <span className="muted">seed</span>}
                          </td>
                          <td className="num">{pct(node.adoption, 0)}</td>
                          <td>{node.unlocked ? <span className="pill on">unlocked</span> : <span className="pill">frontier</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="card">
                <h3>Projects</h3>
                <table>
                  <thead><tr><th>Project</th><th>Organisation</th><th className="num">Researchers</th><th className="num">Funding/mo</th><th>State</th></tr></thead>
                  <tbody>
                    {(data.projects as Json[]).map((project) => (
                      <tr key={project.id}>
                        <td>{project.tech}</td>
                        <td className="muted">{project.organisation}</td>
                        <td className="num">{project.researchers}</td>
                        <td className="num">{money(project.funding_per_month)}</td>
                        <td>{project.active ? <span className="pill on">running</span> : <span className="pill">closed</span>}</td>
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
