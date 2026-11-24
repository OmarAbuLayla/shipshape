import { Link, useParams } from "react-router-dom";

import { Check } from "../components/icons";
import { api } from "../lib/api";
import { capitalize, plural, scoreColor } from "../lib/format";
import { useLoad } from "../lib/hooks";
import { DIMENSIONS, type FixRun, type ScanSummary } from "../lib/types";

/** Before/after view of the last fix run of a scan, with downloads. */
export function FixesPage() {
  const { id = "" } = useParams();
  const data = useLoad(() => Promise.all([api.scan(id), api.fixes(id)]), [id]);

  if (data.error) {
    return (
      <div className="page fixes">
        <h1>No fixes to show</h1>
        <p className="muted">{data.error}</p>
        <Link className="btn" to={`/scans/${id}`}>Back to the review</Link>
      </div>
    );
  }
  if (!data.data) return <div className="page fixes muted">Loading…</div>;
  const [scan, run] = data.data;
  return <FixResult scan={scan} run={run} />;
}

function FixResult({ scan, run }: { scan: ScanSummary; run: FixRun }) {
  const applied = run.outcomes.filter((o) => o.applied).length;
  const skipped = run.outcomes.filter((o) => !o.applied);
  const secondRound = run.outcomes.filter((o) => o.second_round);
  const download = (format: "patch" | "zip") => `/api/scans/${scan.id}/fixes/download?format=${format}`;
  return (
    <div className="page fixes">
      <Link className="back" to={`/scans/${scan.id}`}>← Back to the review</Link>
      <p className="eyebrow">Fixes applied to a copy</p>
      <h1>{scan.name}</h1>
      <p className="muted">
        {plural(applied, "fix", "fixes")} applied to {plural(run.changed_files.length, "file")}
        {skipped.length > 0 ? `, ${skipped.length} skipped` : ""}. Your own files were not changed.
      </p>

      <div className="fix-grid">
        <section className="card grade-card" aria-label="Grade before and after">
          <span className="eyebrow">Grade</span>
          <div className="grade-change">
            <b className="mono">{run.before_grade}</b>
            <span aria-hidden>→</span>
            <b className="mono after">{run.after_grade}</b>
          </div>
        </section>

        <section className="card" aria-label="Scores before and after">
          <table className="score-compare">
            <thead>
              <tr>
                <th>Dimension</th>
                <th>Before</th>
                <th>After</th>
              </tr>
            </thead>
            <tbody>
              {DIMENSIONS.map((d) => {
                const before = run.before_scores[d] ?? 100;
                const after = run.after_scores[d] ?? 100;
                return (
                  <tr key={d}>
                    <td>{capitalize(d)}</td>
                    <td className="mono">{before}</td>
                    <td>
                      <span className="mono" style={{ fontWeight: after !== before ? 700 : 400 }}>{after}</span>
                      <span className="track"><i style={{ width: `${after}%`, background: scoreColor(after) }} /></span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      </div>

      {run.deltas.length > 0 && (
        <section className="sec">
          <h2>What changed</h2>
          <ul className="delta-list">
            {run.deltas.map((d) => (
              <li key={d.check_id}>
                {d.after === 0 && <Check size={14} />}
                <span>
                  <b>{d.title}</b>: {plural(d.before, "place")} before, {d.after === 0 ? "none" : d.after} after
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {secondRound.length > 0 && (
        <section className="sec">
          <h2>Second round</h2>
          <p className="muted small-note">
            These fixes collided with an earlier fix on the same lines, so they were explained again against the
            already fixed code, verified the same way, and then applied.
          </p>
          <ul className="delta-list">
            {secondRound.map((o) => (
              <li key={o.finding}>
                <Check size={14} />
                <span><b>{o.title}</b></span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {skipped.length > 0 && (
        <section className="sec">
          <h2>Skipped</h2>
          <ul className="skipped-list">
            {skipped.map((o) => (
              <li key={o.finding}>
                <b>{o.title}</b> <span className="muted">{o.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {run.patch && (
        <section className="sec">
          <div className="downloads">
            <a className="btn primary" href={download("patch")}>Download patch</a>
            {run.zip_available ? (
              <a className="btn" href={download("zip")}>Download fixed project (.zip)</a>
            ) : (
              run.zip_note && <span className="muted">{run.zip_note}</span>
            )}
          </div>
          <p className="faint small-note">
            Apply the patch inside your project with <code>git apply {scan.name}-shipshape.patch</code>. Every fix was
            checked again after the ones before it: the code parses, the problem is gone and no check finds anything
            new. Shipshape does not run your code, so run your tests once after applying.
          </p>
          <Patch text={run.patch} />
        </section>
      )}
    </div>
  );
}

function Patch({ text }: { text: string }) {
  return (
    <pre className="patch" aria-label="Combined patch">
      {text.split("\n").map((line, i) => {
        const kind = line.startsWith("+++") || line.startsWith("---")
          ? "file"
          : line.startsWith("@@")
            ? "hunk"
            : line.startsWith("+")
              ? "add"
              : line.startsWith("-")
                ? "del"
                : "";
        return (
          <span key={i} className={`ln ${kind}`}>
            {line}
            {"\n"}
          </span>
        );
      })}
    </pre>
  );
}
