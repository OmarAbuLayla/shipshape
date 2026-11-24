import { useMemo } from "react";

import { buildBlockView } from "../lib/blockModel";
import type { Block, Report } from "../lib/types";
import { CodeView, type LineFocus } from "./CodeView";
import { MapView } from "./MapView";

interface Props {
  report: Report;
  scanId: string;
  path: string;
  block: Block | null;
  selectedFinding: number | null;
  focus: LineFocus | null;
  onSelectBlock: (id: string | null) => void;
  onSelectFinding: (index: number) => void;
  onClose: () => void;
}

const noop = () => undefined;

/** One file zoomed in: its blocks as a small map, and the code below. */
export function FileView({ report, scanId, path, block, selectedFinding, focus, onSelectBlock, onSelectFinding, onClose }: Props) {
  const info = report.files?.[path];
  const view = useMemo(() => (info ? buildBlockView(info, report.findings) : null), [info, report.findings]);
  const highlighted = useMemo(
    () =>
      new Set(
        selectedFinding === null || !info ? [] : info.blocks.filter((b) => b.findings.includes(selectedFinding)).map((b) => b.id),
      ),
    [info, selectedFinding],
  );
  const folders = path.split("/").slice(0, -1);
  const file = path.split("/").pop() ?? path;
  const range = block && block.kind !== "module" ? { start: block.start_line, end: block.end_line, label: block.name } : null;

  return (
    <div className="col file-col" aria-label={`Code of ${path}`}>
      <nav className="crumbs" aria-label="Where you are">
        <button className="crumb" onClick={onClose}>Map</button>
        {folders.length > 0 && <span className="crumb-dir mono">{folders.join("/")}/</span>}
        <span aria-hidden>›</span>
        <button className={`crumb mono ${block ? "" : "here"}`} onClick={() => onSelectBlock(null)}>{file}</button>
        {block && (
          <>
            <span aria-hidden>›</span>
            <span className="crumb mono here">{block.name}</span>
          </>
        )}
      </nav>
      {view && view.nodes.length > 0 ? (
        <MapView
          view={view}
          highlighted={highlighted}
          selectedBox={block?.id ?? null}
          onSelectBox={onSelectBlock}
          onToggleFolder={noop}
          onOpenBox={onSelectBlock}
          focus={null}
          legend="blocks"
        />
      ) : (
        <div className="code-note">
          {info ? "No functions or classes in this file." : "This scan was made before function blocks existed. Scan the project again to see them."}
        </div>
      )}
      <CodeView
        scanId={scanId}
        path={path}
        info={info}
        findings={report.findings}
        range={range}
        selectedFinding={selectedFinding}
        focus={focus}
        onShowWhole={() => onSelectBlock(null)}
        onSelectFinding={onSelectFinding}
      />
    </div>
  );
}
