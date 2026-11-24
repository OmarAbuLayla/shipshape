import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Folder, Upload } from "../components/icons";
import { api } from "../lib/api";
import { formatWhen } from "../lib/format";
import { useLoad } from "../lib/hooks";

type Source = "path" | "zip";

export function Home({ llmReady, llmLabel }: { llmReady: boolean; llmLabel: string | null }) {
  const navigate = useNavigate();
  const recent = useLoad(() => api.scans(), []);
  const [source, setSource] = useState<Source>("path");
  const [path, setPath] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [explain, setExplain] = useState(false);
  const [maxFindings, setMaxFindings] = useState(15);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const ready = source === "path" ? path.trim().length > 0 : file !== null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    try {
      const useAI = explain && llmReady;
      const scan =
        source === "path"
          ? await api.scanPath(path.trim().replace(/^"|"$/g, ""), useAI, maxFindings)
          : await api.scanUpload(file!, useAI, maxFindings);
      navigate(`/scans/${scan.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setOver(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  }

  const recentPaths = (recent.data ?? []).slice(0, 5);

  return (
    <div className="page home">
      <section className="home-hero">
        <p className="eyebrow">Shipshape · code review for vibe-coded projects</p>
        <h1 style={{ marginTop: 12 }}>Code is cheap now. Judgment isn't.</h1>
        <p className="lede">
          Point Shipshape at a Python project. It finds what an engineer would object to, shows where on a
          map of your code, and explains each problem in plain language, with fixes that are checked before
          you see them.
        </p>
        <div className="thesis" aria-label="How the bottleneck moved">
          <div><b>2015</b><span>Can you write code?</span></div>
          <div><b>2024</b><span className="strike">Can you write code?</span></div>
          <div><b>2026</b><span>Can you tell if it's good?</span></div>
        </div>

        <form className="card scan-card" onSubmit={submit}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <h2>Scan a project</h2>
            <div className="segmented" role="group" aria-label="Where the project is">
              <button type="button" aria-pressed={source === "path"} onClick={() => setSource("path")}>
                Folder on this computer
              </button>
              <button type="button" aria-pressed={source === "zip"} onClick={() => setSource("zip")}>
                Upload a .zip
              </button>
            </div>
          </div>

          {source === "path" ? (
            <div className="field">
              <label htmlFor="path">Project folder</label>
              <input
                id="path"
                className="input"
                placeholder="C:\Users\you\Projects\my-emg-classifier"
                value={path}
                onChange={(e) => setPath(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
              <span className="hint">Paste the full path. Shipshape reads the files; it never runs them.</span>
            </div>
          ) : (
            <div className="field">
              <span className="label">Project archive</span>
              <div
                className={`dropzone ${over ? "over" : ""}`}
                role="button"
                tabIndex={0}
                onClick={() => fileInput.current?.click()}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && fileInput.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault();
                  setOver(true);
                }}
                onDragLeave={() => setOver(false)}
                onDrop={onDrop}
              >
                <Upload />
                <div style={{ marginTop: 6 }}>
                  {file ? <b>{file.name}</b> : <><b>Drop a .zip here</b> or click to choose one</>}
                </div>
                <div className="hint" style={{ marginTop: 4 }}>
                  Up to 100 MB. The unpacked copy is deleted after the scan.
                </div>
              </div>
              <input
                ref={fileInput}
                type="file"
                accept=".zip,application/zip"
                hidden
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>
          )}

          <label className="explain-row">
            <span className="switch">
              <input
                type="checkbox"
                checked={explain && llmReady}
                disabled={!llmReady}
                onChange={(e) => setExplain(e.target.checked)}
              />
              <span />
            </span>
            <span className="text">
              <b>Explain findings with AI</b>
              {llmReady ? (
                <span className="muted">
                  Sends short code excerpts to {llmLabel} (credentials are removed first). About 0.1 cents per
                  finding; up to{" "}
                  <select
                    aria-label="How many findings to explain"
                    value={maxFindings}
                    onChange={(e) => setMaxFindings(Number(e.target.value))}
                    onClick={(e) => e.preventDefault()}
                    style={{ font: "inherit", border: 0, background: "transparent", color: "var(--accent)", fontWeight: 700 }}
                  >
                    {[5, 10, 15, 25, 50].map((n) => (
                      <option key={n} value={n}>{n}</option>
                    ))}
                  </select>{" "}
                  findings.
                </span>
              ) : (
                <span className="muted">Add an API key to .env to turn this on. Checks work without it.</span>
              )}
            </span>
          </label>

          {error && <div className="form-error" role="alert">{error}</div>}

          <button className="btn primary" type="submit" disabled={!ready || busy} style={{ height: 44 }}>
            {busy ? <span className="spinner" /> : <Folder />}
            {busy ? "Starting…" : "Start scan"}
          </button>
        </form>

        <div className="how">
          <div><span>1 · analyze</span><b>29 checks</b><p>Leakage, seeds, paths, secrets, structure, tests.</p></div>
          <div><span>2 · map</span><b>Your architecture</b><p>Files, imports and problems in one picture.</p></div>
          <div><span>3 · explain</span><b>Verified fixes</b><p>Every fix is re-checked before it is shown.</p></div>
        </div>
      </section>

      <aside className="recent" style={{ paddingTop: 8 }}>
        <h3>Recent scans</h3>
        {recent.error && <p className="muted">{recent.error}</p>}
        {recent.data && recentPaths.length === 0 && (
          <p className="muted" style={{ fontSize: 14 }}>
            Nothing scanned yet. Your scans will be listed here.
          </p>
        )}
        {recentPaths.map((scan) => (
          <Link key={scan.id} to={`/scans/${scan.id}`} className="scan-row">
            <span style={{ minWidth: 0 }}>
              <div className="name">{scan.name}</div>
              <div className="meta">
                {scan.status === "done" ? (
                  <>
                    grade <b>{scan.grade}</b> · {scan.findings} findings{scan.explain ? " · explained" : ""}
                  </>
                ) : (
                  scan.status
                )}{" "}
                · {formatWhen(scan.created_at)}
              </div>
            </span>
            <span className="faint">›</span>
          </Link>
        ))}
        {(recent.data?.length ?? 0) > 5 && <Link to="/history" style={{ fontSize: 14 }}>All scans →</Link>}
      </aside>
    </div>
  );
}
