import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../lib/api";

import { exclusionLines, formatWhen, plural, scoreColor } from "../lib/format";
import { absoluteLine, blockAtLine } from "../lib/blockModel";
import { boxesForFinding, buildViewGraph, defaultExpanded, findingsOfBox } from "../lib/graphModel";
import { DIMENSIONS, type Dimension, type Location, type Report, type ScanSummary } from "../lib/types";
import type { LineFocus } from "./CodeView";
import { DetailPanel, hasVerifiedFix } from "./DetailPanel";
import { IssueList } from "./IssueList";
import { ExportMenu } from "./ExportMenu";
import { FileView } from "./FileView";
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
  const [chosenBox, setSelectedBox] = useState<string | null>(null);
  const [dimension, setDimension] = useState<Dimension | null>(null);
  const [focus, setFocus] = useState<FocusRequest | null>(null);
  // Zoomed into one file: its blocks and code replace the map.
  const [openFile, setOpenFile] = useState<string | null>(null);
  const [blockId, setBlockId] = useState<string | null>(null);
  const [codeFocus, setCodeFocus] = useState<LineFocus | null>(null);
  const fileInfo = openFile ? report.files?.[openFile] : undefined;
  const block = (blockId && fileInfo?.blocks.find((b) => b.id === blockId)) || null;
  const fixable = useMemo(
    () => report.findings.flatMap((f, i) => (hasVerifiedFix(f) ? [i] : [])),
    [report.findings],
  );
  // Every verified fix starts selected; untick the ones you don't want.
  const [chosen, setChosen] = useState<Set<number>>(() => new Set(fixable));
  const [applying, setApplying] = useState(false);
  const [fixError, setFixError] = useState<string | null>(null);
  const navigate = useNavigate();

  const toggleFix = (index: number) =>
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  const applyFixes = async () => {
    setApplying(true);
    setFixError(null);
    try {
      await api.applyFixes(scan.id, [...chosen].sort((a, b) => a - b));
      navigate(`/scans/${scan.id}/fixes`);
    } catch (err) {
      setFixError(err instanceof Error ? err.message : String(err));
      setApplying(false);
    }
  };

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

  // A selected box that disappears (its folder was opened or closed) no longer filters anything.
  const selectedBox = chosenBox && view?.nodes.some((n) => n.id === chosenBox) ? chosenBox : null;

  const highlighted = useMemo(
    () => (view && selected !== null ? boxesForFinding(view, selected) : new Set<string>()),
    [view, selected],
  );
  const visible = useMemo(() => {
    if (openFile) {
      if (block) return block.findings;
      return report.findings.flatMap((f, i) => (f.locations.some((l) => l.path === openFile) ? [i] : []));
    }
    return view && selectedBox ? findingsOfBox(view, selectedBox) : report.findings.map((_, i) => i);
  }, [view, selectedBox, report.findings, openFile, block]);
  const box = view && selectedBox ? (view.nodes.find((n) => n.id === selectedBox) ?? null) : null;

  const selectBox = (id: string | null) => {
    setSelectedBox(id);
    if (id) setSelected(null);
  };
  const locate = (path: string) => {
    const unit = view?.unitOf.get(path);
    if (unit) setFocus((current) => ({ id: unit, request: (current?.request ?? 0) + 1 }));
  };

  /** Scroll the code to ``line`` and select the block holding it (module code: none). */
  const showLine = (path: string, line: number) => {
    const info = report.files?.[path];
    const holder = info ? blockAtLine(info, line) : null;
    setBlockId(holder && holder.kind !== "module" ? holder.id : null);
    setCodeFocus((current) => ({ line, request: (current?.request ?? 0) + 1 }));
  };
  /** Zoom into a file (at a line, if given); files without blocks are shown on the map instead. */
  const openCode = (path: string, line: number | null = null) => {
    if (!report.files?.[path]) {
      locate(path);
      return;
    }
    setOpenFile(path);
    setSelectedBox(null);
    if (line !== null) showLine(path, line);
    else {
      setBlockId(null);
      setCodeFocus(null);
    }
  };
  const openLocation = (location: Location) => openCode(location.path, absoluteLine(location, report.files?.[location.path]));
  const closeFile = () => {
    setOpenFile(null);
    setBlockId(null);
    setCodeFocus(null);
  };
  const selectBlock = (id: string | null) => {
    setBlockId(id);
    if (!id) return;
    setSelected(null);
    const chosen = fileInfo?.blocks.find((b) => b.id === id);
    if (chosen) setCodeFocus((current) => ({ line: chosen.start_line, request: (current?.request ?? 0) + 1 }));
  };
  const selectFinding = (index: number) => {
    setSelected(index);
    if (!openFile) return;
    const here = report.findings[index]?.locations.find((l) => l.path === openFile);
    const line = here ? absoluteLine(here, fileInfo) : null;
    if (line !== null) showLine(openFile, line);
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
          {fixable.length > 0 && (
            <button
              className="btn primary small"
              onClick={applyFixes}
              disabled={applying || chosen.size === 0}
              title="Apply the selected verified fixes to a copy and scan it again. Your files are not changed."
            >
              {applying ? "Applying fixes..." : `Apply ${plural(chosen.size, "fix", "fixes")}`}
            </button>
          )}
          <ExportMenu scanId={scan.id} />
          <Link className="btn small" to="/">New scan</Link>
        </div>
      </header>
      {fixError && <div className="notice fix-error">Couldn't apply the fixes: {fixError}</div>}

      <div className="workspace">
        <IssueList
          findings={report.findings}
          visible={visible}
          selected={selected}
          onSelect={selectFinding}
          dimension={dimension}
          onDimension={setDimension}
          boxLabel={openFile ? (block ? block.name : (openFile.split("/").pop() ?? openFile)) : box ? box.label : null}
          onClearBox={() => (openFile ? (block ? setBlockId(null) : closeFile()) : setSelectedBox(null))}
        />
        {openFile ? (
          <FileView
            report={report}
            scanId={scan.id}
            path={openFile}
            block={block}
            selectedFinding={selected}
            focus={codeFocus}
            onSelectBlock={selectBlock}
            onSelectFinding={selectFinding}
            onClose={closeFile}
          />
        ) : view ? (
          <MapView
            view={view}
            highlighted={highlighted}
            selectedBox={selectedBox}
            onSelectBox={selectBox}
            onToggleFolder={toggleFolder}
            onOpenBox={(id) => openCode(id)}
            focus={focus}
          />
        ) : (
          <div className="col map-col empty">No map available for this scan.</div>
        )}
        <DetailPanel
          report={report}
          selected={selected}
          box={openFile ? null : box}
          block={block}
          chosen={chosen}
          onToggleFix={toggleFix}
          onSelect={selectFinding}
          onOpenLocation={openLocation}
          onOpenFile={(path) => openCode(path)}
          onSelectBlock={selectBlock}
        />
      </div>
    </div>
  );
}
