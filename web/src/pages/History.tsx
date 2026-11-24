import { Link, useNavigate } from "react-router-dom";

import { Trash } from "../components/icons";
import { api } from "../lib/api";
import { formatWhen } from "../lib/format";
import { useLoad } from "../lib/hooks";

export function History() {
  const scans = useLoad(() => api.scans(), []);
  const navigate = useNavigate();

  async function remove(id: string, name: string) {
    if (!window.confirm(`Remove the scan of “${name}” from history? Your code is not touched.`)) return;
    await api.remove(id);
    scans.reload();
  }

  return (
    <div className="page history">
      <p className="eyebrow">History</p>
      <h1>Past scans</h1>
      {scans.error && <div className="form-error">{scans.error}</div>}
      {scans.data && scans.data.length === 0 && (
        <div className="card empty">
          No scans yet. <Link to="/">Scan your first project</Link>.
        </div>
      )}
      {scans.data && scans.data.length > 0 && (
        <div className="card" style={{ padding: "14px 8px 6px", overflowX: "auto" }}>
          <table className="history-table">
            <thead>
              <tr>
                <th>Grade</th>
                <th>Project</th>
                <th>Findings</th>
                <th>AI</th>
                <th>Source</th>
                <th>When</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {scans.data.map((scan) => (
                <tr key={scan.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/scans/${scan.id}`)}>
                  <td>
                    {scan.grade ? (
                      <span className={`grade small ${scan.grade}`}>{scan.grade}</span>
                    ) : (
                      <span className={`chip ${scan.status === "failed" ? "rejected" : "neutral"}`}>{scan.status}</span>
                    )}
                  </td>
                  <td style={{ fontWeight: 700 }}>{scan.name}</td>
                  <td className="mono">{scan.findings ?? "–"}</td>
                  <td>{scan.explain ? <span className="chip accent">explained</span> : <span className="faint">–</span>}</td>
                  <td className="muted">{scan.source === "path" ? "folder" : "zip"}</td>
                  <td className="muted">{formatWhen(scan.created_at)}</td>
                  <td style={{ textAlign: "right" }}>
                    <button
                      className="btn ghost small"
                      aria-label={`Remove ${scan.name} from history`}
                      onClick={(e) => {
                        e.stopPropagation();
                        void remove(scan.id, scan.name);
                      }}
                    >
                      <Trash />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
