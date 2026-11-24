import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { exclusionLines, formatWhen, plural, scoreColor } from "../lib/format";
import { boxesForFinding, buildViewGraph, defaultExpanded, findingsOfBox } from "../lib/graphModel";
import { DIMENSIONS, type Dimension, type Report, type ScanSummary } from "../lib/types";
import { DetailPanel } from "./DetailPanel";
import { IssueList } from "./IssueList";
import { ExportMenu } from "./ExportMenu";
import { MapView, type FocusRequest } from "./MapView";

const SHORT_LABEL: Record<Dimension, string> = {
  correctness: "Correctness",
  structure: "Structure",
  reproducibility: "Reproducible",
  readability: "Readability",
  testing: "Testing",
  security: "Security",
};

export function Review({ report, scan }: { report: Report; scan: ScanSummary }) {
  const graph = report.graph;
  const [expanded, setExpanded] = useState<Set<string>>(() => (graph ? defaultExpanded(graph) : new Set()));
  const [showTests] = useState(true);
  const [selected, setSelected] = useState<number | null>(null); // start on the overview
  const [selectedBox, setSelectedBox] = useState<string | null>(null);
  const [dimension, setDimension] = useState<Dimension | null>(null);
  const [focus, setFocus] = useState<FocusRequest | null>(null);

  const view = useMemo(
    () => (graph ? buildViewGraph(graph, report.findings, { expanded, showTests }) : null),
    [graph, report.findings, expanded, showTests],
  );

  const toggleFolder = useCallback((folder: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(folder)) next.delete(folder);
      else next.add(folder);
      return next;
    });
  }, []);

  // If the selected box disappears (folder opened or closed), drop the box filter.
  useEffect(() => {
    if (selectedBox && view && !view.nodes.some((n) => n.id === selectedBox)) setSelectedBox(null);
  }, [view, selectedBox]);

  const highlighted = useMemo(
    () => (view && selected !== null ? boxesForFinding(view, selected) : new Set<string>()),
    [view, selected],
  );
  const visible = useMemo(
    () => (view && selectedBox ? findingsOfBox(view, selectedBox) : report.findings.map((_, i) => i)),
    [view, selectedBox, report.findings],
  );
  const box = view && selectedBox ? (view.nodes.find((n) => n.id === selectedBox) ?? null) : null;

  const selectBox = (id: string | null) => {
    setSelectedBox(id);
    if (id) setSelected(null);
  };
  const locate = (path: string) => {
    const unit = view?.unitOf.get(path);
    if (unit) setFocus((current) => ({ id: unit, request: (current?.request ?? 0) + 1 }));
  };

  const s = report.stats;
  const excluded = exclusionLines(report.exclusions);
  return (
    <div className="review">
      <header className="review-head">
        <div className="review-title">
          <div style={{ minWidth: 0 }}>
            <h1>{report.project_name}</h1>
            <div className="meta">
              <span title="Overall grade (rough guide)">grade <b className="mono">{report.grade}</b></span> ·{" "}
              {plural(s.python_files, "Python file")}
              {s.notebooks ? `, ${plural(s.notebooks, "notebook")}` : ""} · {s.lines_of_code.toLocaleString()} lines ·{" "}
              {plural(report.findings.length, "finding")} · scanned {formatWhen(scan.created_at)}
              {report.explain_stats ? ` · explained by ${report.explain_stats.model}` : ""}
              {excluded.length > 0 && (
                <span title={excluded.join("\n")}> · some files and lines left out on request</span>
              )}
            </div>
          </div>
        </div>
        <div className="scores" aria-label="Scores per dimension">
          {DIMENSIONS.map((d) => {
            const score = report.scores[d] ?? 100;
            return (
              <button
                key={d}
                className="score"
                onClick={() => setDimension(dimension === d ? null : d)}
                style={{ border: 0, background: "none", padding: 0, cursor: "pointer", textAlign: "left", opacity: dimension && dimension !== d ? 0.45 : 1 }}
                aria-pressed={dimension === d}
                title={`Show only ${d} findings`}
              >
                <span className="lbl"><span>{SHORT_LABEL[d]}</span> <b>{score}</b></span>
                <span className="track"><i style={{ width: `${score}%`, background: scoreColor(score) }} /></span>
              </button>
            );
          })}
        </div>
        <div className="actions">
          <ExportMenu scanId={scan.id} />
          <Link className="btn small" to="/">New scan</Link>
        </div>
      </header>

      <div className="workspace">
        <IssueList
          findings={report.findings}
          visible={visible}
          selected={selected}
          onSelect={(i) => setSelected(i)}
          dimension={dimension}
          onDimension={setDimension}
          boxLabel={box ? box.label : null}
          onClearBox={() => setSelectedBox(null)}
        />
        {view ? (
          <MapView
            view={view}
            highlighted={highlighted}
            selectedBox={selectedBox}
            onSelectBox={selectBox}
            onToggleFolder={toggleFolder}
            focus={focus}
          />
        ) : (
          <div className="col map-col empty">No map available for this scan.</div>
        )}
        <DetailPanel
          report={report}
          selected={selected}
          box={box}
          onSelect={(i) => {
            setSelected(i);
          }}
          onLocate={locate}
        />
      </div>
    </div>
  );
}
