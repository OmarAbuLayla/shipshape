import { Link } from "react-router-dom";

import { Check } from "../components/icons";
import { api } from "../lib/api";
import { capitalize, formatWhen, plural } from "../lib/format";
import { useLoad } from "../lib/hooks";
import type { ConceptStat, Profile as ProfileData } from "../lib/types";

/** Which concepts keep coming up across your projects, from the local scan history. */
export function Profile() {
  const profile = useLoad(() => api.profile(), []);
  return (
    <div className="page profile-page">
      <p className="eyebrow">Profile</p>
      <h1>What keeps coming up</h1>
      {profile.error && <div className="form-error">{profile.error}</div>}
      {profile.data && <ProfileBody data={profile.data} />}
    </div>
  );
}

function ProfileBody({ data }: { data: ProfileData }) {
  if (data.scans === 0) {
    return (
      <div className="card empty">
        No scans yet. <Link to="/">Scan a project</Link> and your profile builds up from there.
      </div>
    );
  }
  const current = data.concepts.filter((c) => c.projects.length > 0);
  const resolved = data.concepts.filter((c) => c.projects.length === 0);
  const total = data.projects.length;
  return (
    <>
      <p className="muted lead">
        Built from {plural(data.scans, "scan")} of {plural(total, "project")} on this computer; nothing leaves it. Each
        project counts with its latest scan. To leave a scan out, remove it in <Link to="/history">History</Link>.
      </p>

      <section className="sec">
        <h2>Concepts in your projects now</h2>
        {current.length === 0 ? (
          <p className="muted">Your latest scans have no findings. Nothing to work on right now.</p>
        ) : (
          <div className="concept-rows">
            {current.map((c) => <ConceptRow key={c.concept} stat={c} total={total} />)}
          </div>
        )}
      </section>

      {resolved.length > 0 && (
        <section className="sec">
          <h2>Resolved</h2>
          <p className="muted small">Found in an earlier scan of a project, gone in its latest one.</p>
          <ul className="resolved-list">
            {resolved.map((c) => (
              <li key={c.concept}>
                <Check size={14} />
                <span>
                  {c.lesson ? <Link to={`/lessons/${c.lesson}`}>{c.concept}</Link> : c.concept}
                  <span className="faint"> · in {c.resolved_in.join(", ")}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="sec">
        <h2>Projects</h2>
        <div className="card" style={{ padding: "8px 8px 4px", overflowX: "auto" }}>
          <table className="history-table">
            <thead>
              <tr>
                <th>Project</th>
                <th>Scans</th>
                <th>Grade</th>
                <th>Findings now</th>
                <th>Last scanned</th>
              </tr>
            </thead>
            <tbody>
              {data.projects.map((p) => (
                <tr key={p.name}>
                  <td style={{ fontWeight: 700 }}><Link to={`/scans/${p.latest_scan}`}>{p.name}</Link></td>
                  <td className="mono">{p.scans}</td>
                  <td className="mono">{p.scans > 1 && p.first_grade !== p.latest_grade ? `${p.first_grade} → ${p.latest_grade}` : p.latest_grade}</td>
                  <td className="mono">{p.findings}</td>
                  <td className="muted">{formatWhen(p.latest_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function ConceptRow({ stat, total }: { stat: ConceptStat; total: number }) {
  return (
    <div className="concept-row">
      <div className="concept-name">
        <span className={`dot ${stat.severity}`} aria-label={stat.severity} />
        {stat.lesson ? <Link to={`/lessons/${stat.lesson}`}>{stat.concept}</Link> : <b>{stat.concept}</b>}
        <span className="chip neutral">{capitalize(stat.dimension)}</span>
      </div>
      <div className="concept-share" title={stat.projects.join(", ")}>
        <span className="track"><i style={{ width: `${(stat.projects.length / total) * 100}%` }} /></span>
        <span className="faint">
          in {stat.projects.length} of {total} {total === 1 ? "project" : "projects"} · {plural(stat.places, "place")}
        </span>
      </div>
      <div className="concept-projects faint">
        {stat.projects.join(", ")}
        {stat.resolved_in.length > 0 && <span className="resolved-note"> · resolved in {stat.resolved_in.join(", ")}</span>}
      </div>
    </div>
  );
}
