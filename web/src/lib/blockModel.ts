// Turns one file's blocks into a graph the map component can draw: functions as boxes, classes
// and notebook cells as containers around their methods and functions, calls as arrows.

import { plural, worstSeverity } from "./format";
import type { ViewEdge, ViewGraph, ViewKind, ViewNode } from "./graphModel";
import type { Block, FileInfo, Finding, Location } from "./types";

/** Short label: methods drop their class (they are drawn inside it). */
function blockLabel(block: Block): string {
  return block.kind === "method" ? block.name.slice(block.name.indexOf(".") + 1) : block.name;
}

function blockSub(block: Block): string {
  if (block.kind === "module") return `${plural(block.lines_of_code, "line")} of top-level code`;
  if (block.kind === "cell") return plural(block.lines_of_code, "line");
  const cc = block.complexity > 1 ? ` · complexity ${block.complexity}` : "";
  return `${plural(block.lines_of_code, "line")}${cc}`;
}

const KIND: Record<Block["kind"], ViewKind> = {
  function: "file",
  method: "file",
  class: "file",
  cell: "notebook",
  module: "config",
};

/** Blocks worth drawing: module code only when it holds code or findings. */
export function visibleBlocks(info: FileInfo): Block[] {
  return info.blocks.filter((b) => b.kind !== "module" || b.lines_of_code > 0 || b.findings.length > 0);
}

export function buildBlockView(info: FileInfo, findings: Finding[]): ViewGraph {
  const blocks = visibleBlocks(info);
  const hasChildren = new Set(blocks.map((b) => b.parent).filter((p): p is string => !!p));
  const ids = new Set(blocks.map((b) => b.id));
  const nodes: ViewNode[] = blocks.map((b) => ({
    id: b.id,
    kind: hasChildren.has(b.id) ? "group" : KIND[b.kind],
    label: blockLabel(b),
    sub: blockSub(b),
    severity: worstSeverity(b.findings.map((i) => findings[i]?.severity)),
    findings: [...b.findings],
    members: [b.id],
    parent: b.parent && ids.has(b.parent) ? b.parent : undefined,
  }));

  const parentOf = new Map(blocks.map((b) => [b.id, b.parent]));
  const isAncestor = (maybe: string, of: string): boolean => {
    for (let p = parentOf.get(of); p; p = parentOf.get(p)) if (p === maybe) return true;
    return false;
  };
  const edges: ViewEdge[] = [];
  for (const b of blocks) {
    for (const target of b.calls) {
      // A method calling its own class (or a cell calling a function it defines) is nesting, not
      // an arrow: the layout cannot route an edge from a container into itself.
      if (!ids.has(target) || target === b.id || isAncestor(target, b.id) || isAncestor(b.id, target)) continue;
      edges.push({ id: `c${edges.length}`, source: b.id, target, kind: "import", count: 1 });
    }
  }
  // Containers before their children (React Flow requirement).
  const ordered = [...nodes].sort((a, b) => Number(b.kind === "group") - Number(a.kind === "group"));
  return { nodes: ordered, edges, unitOf: new Map(blocks.map((b) => [b.id, b.id])) };
}

/** A location's line in the scanned text (notebook cell lines translated back). */
export function absoluteLine(location: Location, info: FileInfo | undefined): number | null {
  if (location.start_line === null) return null;
  if (location.cell !== null && info && info.cell_starts.length >= location.cell) {
    return info.cell_starts[location.cell - 1]! + location.start_line - 1;
  }
  return location.start_line;
}

/** Scanned-text lines flagged in ``path``, with the indices of the findings on each. */
export function flaggedLines(findings: Finding[], path: string, info: FileInfo | undefined): Map<number, number[]> {
  const lines = new Map<number, number[]>();
  findings.forEach((finding, index) => {
    for (const location of finding.locations) {
      if (location.path !== path) continue;
      const line = absoluteLine(location, info);
      if (line === null) continue;
      const end = location.end_line !== null && location.cell === null ? location.end_line : line;
      // Mark the first line of long ranges (a whole function) only; the block shows the rest.
      for (const l of end - line <= 3 ? range(line, end) : [line]) {
        const at = lines.get(l) ?? [];
        if (!at.includes(index)) at.push(index);
        lines.set(l, at);
      }
    }
  });
  return lines;
}

function range(from: number, to: number): number[] {
  return Array.from({ length: to - from + 1 }, (_, i) => from + i);
}

/** The block of ``path`` that holds a scanned line (innermost; module code as a fallback). */
export function blockAtLine(info: FileInfo, line: number): Block | null {
  const containing = info.blocks.filter((b) => b.kind !== "module" && b.start_line <= line && line <= b.end_line);
  if (containing.length) return containing.reduce((a, b) => (b.end_line - b.start_line < a.end_line - a.start_line ? b : a));
  return info.blocks.find((b) => b.kind === "module") ?? null;
}
