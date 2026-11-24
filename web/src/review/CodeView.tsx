import { useEffect, useMemo, useRef } from "react";

import { api } from "../lib/api";
import { flaggedLines } from "../lib/blockModel";
import { worstSeverity } from "../lib/format";
import { highlightPython } from "../lib/highlight";
import { useLoad } from "../lib/hooks";
import type { FileInfo, Finding } from "../lib/types";

/** Scroll request: ``request`` changes on every click so repeats still scroll. */
export interface LineFocus {
  line: number;
  request: number;
}

interface Props {
  scanId: string;
  path: string;
  info: FileInfo | undefined;
  findings: Finding[];
  range: { start: number; end: number; label: string } | null; // the selected block, if any
  selectedFinding: number | null;
  focus: LineFocus | null;
  onShowWhole: () => void;
  onSelectFinding: (index: number) => void;
}

/** Read-only code of one scanned file, with flagged lines marked. */
export function CodeView({ scanId, path, info, findings, range, selectedFinding, focus, onShowWhole, onSelectFinding }: Props) {
  const source = useLoad(() => api.source(scanId, path), [scanId, path]);
  const body = useRef<HTMLDivElement>(null);
  const flagged = useMemo(() => flaggedLines(findings, path, info), [findings, path, info]);
  const lines = useMemo(() => source.data?.text.replace(/\n$/, "").split("\n") ?? [], [source.data]);
  const cellOf = useMemo(() => new Map((info?.cell_starts ?? []).map((line, i) => [line, i + 1])), [info]);

  useEffect(() => {
    if (!focus || !body.current || !source.data) return;
    body.current.querySelector(`[data-line="${focus.line}"]`)?.scrollIntoView({ block: "center" });
  }, [focus, source.data, range]);

  if (source.error) {
    return <div className="code-view"><div className="code-note">{source.error}</div></div>;
  }
  if (!source.data) return <div className="code-view"><div className="code-note faint">Loading code…</div></div>;

  const first = range ? range.start : 1;
  const last = range ? Math.min(range.end, lines.length) : lines.length;
  return (
    <div className="code-view">
      <div className="code-bar">
        <span className="mono">
          {range ? `${range.label} · lines ${first}–${last}` : `${path} · ${lines.length} lines`}
        </span>
        {range && (
          <button className="btn ghost small" onClick={onShowWhole}>
            Show the whole file
          </button>
        )}
      </div>
      {source.data.changed && (
        <div className="code-note warn">
          This file changed since the scan, so the marked lines may be off. Scan again for exact positions.
        </div>
      )}
      <div className="code-body" ref={body}>
        {lines.slice(first - 1, last).map((text, i) => {
          const n = first + i;
          const here = flagged.get(n) ?? [];
          const severity = worstSeverity(here.map((f) => findings[f]?.severity));
          const selected = selectedFinding !== null && here.includes(selectedFinding);
          const cell = cellOf.get(n);
          return (
            <div key={n}>
              {cell !== undefined && <div className="cell-sep">cell {cell}</div>}
              <div
                className={`cl ${severity ?? ""} ${selected ? "sel" : ""} ${here.length ? "flagged" : ""}`}
                data-line={n}
                title={here.map((f) => findings[f]?.title).join("\n") || undefined}
                onClick={here.length ? () => onSelectFinding(here[0]!) : undefined}
              >
                <span className="no">{n}</span>
                <span className="src">
                  {highlightPython(text).map((token, k) =>
                    token.kind === "plain" ? token.text : <span key={k} className={`tok-${token.kind}`}>{token.text}</span>,
                  )}
                  {"\n"}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
