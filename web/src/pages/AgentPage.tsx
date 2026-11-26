import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Check } from "../components/icons";
import { api, ApiError } from "../lib/api";
import { capitalize, plural, scoreColor } from "../lib/format";
import { useHealth, useLoad, usePoll } from "../lib/hooks";
import { DIMENSIONS, type AgentRun, type AgentState, type AgentStep, type ScanSummary } from "../lib/types";
import { Patch } from "./FixesPage";

const TOOL_LABEL: Record<string, string> = {
  list_findings: "Looked at the findings",
  read_file: "Read",
  propose_fix: "Proposed a fix",
  finish: "Finished",
};

/** Let the agent work on a scanned project, watch its steps live, then see what it changed. */
export function AgentPage() {
  const { id = "" } = useParams();
  const scan = useLoad(() => api.scan(id), [id]);
  const health = useHealth();
  const [state, setState] = useState<AgentState | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const running = !loaded || state?.status === "running";
  usePoll(
    async () => {
      try {
        const next = await api.agent(id);
        setState(next);
        setLoaded(true);
        return next.status !== "running";
      } catch (e) {
        setLoaded(true);
        if (e instanceof ApiError && e.status === 404) return true; // never run: show the start card
        throw e;
      }
    },
    1000,
    running,
  );

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      setState(await api.startAgent(id));
      setLoaded(false); // poll again until it finishes
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  };

  if (scan.error) {
    return (
      <div className="page fixes">
        <h1>No such scan</h1>
        <p className="muted">{scan.error}</p>
        <Link className="btn" to="/">Back</Link>
      </div>
    );
  }
  if (!scan.data) return <div className="page fixes muted">Loading…</div>;
  const llm = health.data?.llm;
  const idle = loaded && (state === null || state.status !== "running");

  return (
    <div className="page fixes agent">
      <Link className="back" to={`/scans/${id}`}>← Back to the review</Link>
      <p className="eyebrow">Shipshape agent</p>
      <h1>{scan.data.name}</h1>
      <p className="muted">
        The agent reads your code and proposes one fix at a time. Shipshape checks every fix (the code still
        parses, the problem is gone, nothing new appears) and applies only those that pass, to a copy. Your own
        files are not changed.
      </p>

      {idle && (
        <StartCard
          llmLabel={llm?.configured ? `${llm.provider ?? "AI"} (${llm.model ?? "default model"})` : null}
          again={state !== null}
          starting={starting}
          onStart={start}
        />
      )}
      {error && <div className="notice">Couldn't start the agent: {error}</div>}
      {state?.status === "failed" && <div className="notice">The agent stopped: {state.error}</div>}

      {state && state.steps.length > 0 && <Timeline state={state} />}
      {state?.status === "running" && state.steps.length === 0 && (
        <p className="muted agent-wait">Starting: the agent is looking at the findings…</p>
      )}
      {state?.status === "done" && state.run && <Result scan={scan.data} state={state} run={state.run} />}
    </div>
  );
}

function StartCard(props: { llmLabel: string | null; again: boolean; starting: boolean; onStart: () => void }) {
  return (
    <section className="card agent-start" aria-label="Start the agent">
      {props.llmLabel ? (
        <>
          <p>
            Uses <b>{props.llmLabel}</b>. Limits: 30 model turns and about $0.10; it stops earlier when it is done.
            The code it reads is sent to that provider, with credentials hidden.
          </p>
          <button className="btn primary" onClick={props.onStart} disabled={props.starting}>
            {props.starting ? "Starting…" : props.again ? "Run the agent again" : "Start the agent"}
          </button>
        </>
      ) : (
        <p className="muted">
          The agent needs an LLM key. Copy <code>.env.example</code> to <code>.env</code>, add a key, and restart{" "}
          <code>shipshape-api</code>.
        </p>
      )}
    </section>
  );
}

function Timeline({ state }: { state: AgentState }) {
  return (
    <section className="sec" aria-label="Agent steps">
      <h2>
        Steps{" "}
        <span className="muted small">
          {state.status === "running" ? "· working…" : `· ${plural(state.steps.length, "step")}`}
        </span>
      </h2>
      <ol className="agent-steps">
        {state.steps.map((step) => (
          <StepRow key={step.number} step={step} />
        ))}
        {state.status === "running" && <li className="agent-step pending">…</li>}
      </ol>
    </section>
  );
}

function StepRow({ step }: { step: AgentStep }) {
  const kind = step.tool === "propose_fix" ? (step.ok ? "passed" : "rejected") : step.ok ? "" : "error";
  return (
    <li className={`agent-step ${kind}`}>
      <span className="num mono">{step.number}</span>
      <span className="what">
        <b>{TOOL_LABEL[step.tool] ?? step.tool}</b> <span className="mono step-detail">{step.detail}</span>
        {!step.ok && step.result && <span className="reason">{step.result}</span>}
      </span>
      {step.tool === "propose_fix" && <span className={`tag ${kind}`}>{step.ok ? "passed" : "rejected"}</span>}
    </li>
  );
}

function Result({ scan, state, run }: { scan: ScanSummary; state: AgentState; run: AgentRun }) {
  const download = (format: "patch" | "zip") => `/api/scans/${scan.id}/agent/download?format=${format}`;
  const cost = run.estimated_cost_usd !== null ? `, about $${run.estimated_cost_usd.toFixed(3)}` : "";
  return (
    <>
      <section className="sec">
        <h2>Result</h2>
        <p className="muted">
          Stopped: {run.stopped_because}. {plural(run.fixes_applied.length, "verified fix", "verified fixes")} applied
          to {plural(run.changed_files.length, "file")} ({plural(run.turns, "model turn")}
          {cost}).
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
      </section>

      {run.summary && (
        <section className="sec">
          <h2>The agent's summary</h2>
          <p className="agent-summary">{run.summary}</p>
        </section>
      )}

      {run.fixes_applied.length > 0 && (
        <section className="sec">
          <h2>Fixes applied</h2>
          <ul className="delta-list">
            {run.fixes_applied.map((fix) => (
              <li key={fix}>
                <Check size={14} />
                <span>{fix}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {run.gave_up_on.length > 0 && (
        <p className="muted small-note">Stopped trying after repeated rejections: {run.gave_up_on.join(", ")}.</p>
      )}

      {run.patch && (
        <section className="sec">
          <div className="downloads">
            <a className="btn primary" href={download("patch")}>Download patch</a>
            {state.zip_available && <a className="btn" href={download("zip")}>Download fixed project (.zip)</a>}
          </div>
          <p className="faint small-note">
            Apply the patch inside your project with <code>git apply {scan.name}-agent.patch</code>. Shipshape does
            not run your code, so run your tests once after applying.
          </p>
          <Patch text={run.patch} />
        </section>
      )}
    </>
  );
}
