import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../lib/api";
import { usePoll } from "../lib/hooks";
import type { Report, ScanSummary } from "../lib/types";
// The review screen (map + layout engine) is large; load it only when a report is shown.
const Review = lazy(() => import("../review/Review").then((m) => ({ default: m.Review })));

export function ScanPage() {
  const { id = "" } = useParams();
  // A new id gets a fresh component, so nothing from the previous scan lingers.
  return <ScanView key={id} id={id} />;
}

function ScanView({ id }: { id: string }) {
  const [scan, setScan] = useState<ScanSummary | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  usePoll(
    async () => {
      try {
        const current = await api.scan(id);
        setScan(current);
        if (current.status === "done") {
          setReport(await api.report(id));
          return true;
        }
        return current.status === "failed";
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        return true;
      }
    },
    700,
    !!id,
  );

  if (error) {
    return (
      <div className="progress-wrap">
        <div className="card progress-card">
          <h1>Can't open this scan</h1>
          <p className="muted">{error}</p>
          <Link className="btn" to="/">Start a new scan</Link>
        </div>
      </div>
    );
  }
  if (report && scan) {
    return (
      <Suspense fallback={<Progress scan={scan} />}>
        <Review report={report} scan={scan} />
      </Suspense>
    );
  }
  return <Progress scan={scan} />;
}

function Progress({ scan }: { scan: ScanSummary | null }) {
  const [started] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, []);

  if (scan?.status === "failed") {
    return (
      <div className="progress-wrap">
        <div className="card progress-card">
          <span className="chip rejected" style={{ justifySelf: "start" }}>Scan failed</span>
          <h1>{scan.name}</h1>
          <p className="muted">{scan.error}</p>
          <Link className="btn" to="/">Try again</Link>
        </div>
      </div>
    );
  }

  const explaining = scan?.progress.startsWith("Explaining") ?? false;
  const match = scan?.progress.match(/(\d+) of (\d+)/);
  const fraction = match ? Number(match[1]) / Math.max(Number(match[2]), 1) : null;
  const steps = [
    { label: "Reading the project", done: scan !== null && scan.status !== "queued" },
    { label: "Running 29 checks and drawing the map", done: explaining },
    ...(scan?.explain ? [{ label: scan.progress && explaining ? scan.progress : "Explaining findings with AI", done: false }] : []),
  ];
  const current = steps.findIndex((s) => !s.done);

  return (
    <div className="progress-wrap">
      <div className="card progress-card" aria-live="polite">
        <p className="eyebrow">Scanning</p>
        <h1>{scan?.name ?? "Starting…"}</h1>
        <div className="steps">
          {steps.map((step, index) => (
            <div key={step.label} className={`step ${step.done ? "done" : index === current ? "" : "todo"}`}>
              {index === current ? <span className="spinner" /> : <span className="dot" />}
              {step.label}
            </div>
          ))}
        </div>
        <div className={`bar ${fraction === null ? "indeterminate" : ""}`}>
          <i style={fraction === null ? undefined : { width: `${Math.max(fraction * 100, 4)}%` }} />
        </div>
        <p className="faint" style={{ fontSize: 13 }}>
          {Math.round((now - started) / 1000)} s · nothing in the project is executed
        </p>
      </div>
    </div>
  );
}
