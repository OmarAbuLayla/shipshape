// Turns the report's graph into what the map shows: collapsed folders as single boxes,
// expanded folders as containers with their files inside, edges merged and counted.

import { worstSeverity } from "./format";
import type { EdgeKind, Finding, GraphNode, ProjectGraph, Severity } from "./types";

export type ViewKind = "file" | "folder" | "group" | "missing" | "external" | "config" | "test" | "notebook";

export interface ViewNode {
  id: string;
  kind: ViewKind;
  label: string;
  sub: string;
  severity: Severity | null;
  findings: number[]; // indices into report.findings, unique and sorted
  members: string[]; // graph node ids drawn by this box
  parent?: string; // id of the containing group (expanded folder)
  folder?: string; // folder path, for folder and group boxes
}

export interface ViewEdge {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
  count: number;
}

export interface ViewGraph {
  nodes: ViewNode[];
  edges: ViewEdge[];
  unitOf: Map<string, string>; // graph node id (or folder path) -> id of the box showing it
}

export interface ViewOptions {
  expanded: Set<string>;
  showTests: boolean;
}

const CODE_KINDS = new Set(["module", "notebook", "test", "config"]);
export const AUTO_EXPAND_LIMIT = 25;

export const folderId = (path: string) => `folder:${path}`;
export const groupId = (path: string) => `group:${path}`;

/** Folders to expand initially: all of them for small projects, none for large ones. */
export function defaultExpanded(graph: ProjectGraph): Set<string> {
  const code = graph.nodes.filter((n) => n.kind === "module" || n.kind === "notebook" || n.kind === "test");
  if (code.length > AUTO_EXPAND_LIMIT) return new Set();
  return new Set(graph.nodes.filter((n) => n.kind === "folder").map((n) => n.id));
}

function isClutter(node: GraphNode, degree: Map<string, number>): boolean {
  return node.label === "__init__.py" && node.findings.length === 0 && !degree.get(node.id);
}

function fileKind(node: GraphNode): ViewKind {
  switch (node.kind) {
    case "missing":
    case "external":
    case "config":
    case "test":
    case "notebook":
      return node.kind;
    default:
      return "file";
  }
}

function fileSub(node: GraphNode): string {
  if (node.kind === "missing") return "missing";
  if (node.kind === "external") return "data outside the project";
  if (node.kind === "config") return "config";
  const role = node.role && node.role !== "library" ? ` · ${node.role}` : "";
  return `${node.lines_of_code} lines${role}`;
}

function unique(values: number[]): number[] {
  return [...new Set(values)].sort((a, b) => a - b);
}

export function buildViewGraph(graph: ProjectGraph, findings: Finding[], options: ViewOptions): ViewGraph {
  const degree = new Map<string, number>();
  for (const edge of graph.edges) {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  }
  const folders = new Map(graph.nodes.filter((n) => n.kind === "folder").map((n) => [n.id, n]));
  const nodes = new Map<string, ViewNode>();
  const unitOf = new Map<string, string>();

  const severityOf = (indices: number[]) => worstSeverity(indices.map((i) => findings[i]?.severity));

  for (const node of graph.nodes) {
    if (node.kind === "folder" || isClutter(node, degree)) continue;
    if (!options.showTests && node.kind === "test") continue;
    const parent = node.parent;
    const collapsible = parent !== null && CODE_KINDS.has(node.kind);
    if (collapsible && !options.expanded.has(parent)) {
      const id = folderId(parent);
      let box = nodes.get(id);
      if (!box) {
        box = { id, kind: "folder", label: `${parent}/`, sub: "", severity: null, findings: [], members: [], folder: parent };
        nodes.set(id, box);
      }
      box.members.push(node.id);
      box.findings.push(...node.findings);
      unitOf.set(node.id, id);
      continue;
    }
    const box: ViewNode = {
      id: node.id,
      kind: fileKind(node),
      label: node.label,
      sub: fileSub(node),
      severity: node.worst_severity,
      findings: [...node.findings],
      members: [node.id],
    };
    if (collapsible) {
      box.parent = groupId(parent);
      const group = nodes.get(box.parent) ?? {
        id: box.parent, kind: "group" as const, label: `${parent}/`, sub: "", severity: null,
        findings: [], members: [], folder: parent,
      };
      group.members.push(node.id);
      nodes.set(group.id, group);
    }
    nodes.set(box.id, box);
    unitOf.set(node.id, box.id);
  }

  // Folder-level findings (e.g. a duplicated package) belong to the folder's box.
  for (const box of nodes.values()) {
    if (!box.folder) continue;
    const folder = folders.get(box.folder);
    if (folder) box.findings.push(...folder.findings);
    unitOf.set(box.folder, box.id);
    box.findings = unique(box.findings);
    box.severity = severityOf(box.findings);
    if (box.kind === "folder") {
      const lines = box.members.reduce((sum, id) => sum + (graph.nodes.find((n) => n.id === id)?.lines_of_code ?? 0), 0);
      box.sub = `${box.members.length} ${box.members.length === 1 ? "file" : "files"} · ${lines} lines`;
    }
  }

  const counts = new Map<string, ViewEdge>();
  for (const edge of graph.edges) {
    const source = unitOf.get(edge.source);
    const target = unitOf.get(edge.target);
    if (!source || !target || source === target) continue;
    const key = `${source}|${target}|${edge.kind}`;
    const existing = counts.get(key);
    if (existing) existing.count += 1;
    else counts.set(key, { id: `e${counts.size}`, source, target, kind: edge.kind, count: 1 });
  }

  // Containers must come before their children (React Flow requirement).
  const ordered = [...nodes.values()].sort((a, b) => Number(b.kind === "group") - Number(a.kind === "group"));
  return { nodes: ordered, edges: [...counts.values()], unitOf };
}

/** Boxes that carry a finding (by its index in report.findings), for highlighting. */
export function boxesForFinding(view: ViewGraph, findingIndex: number): Set<string> {
  return new Set(view.nodes.filter((n) => n.findings.includes(findingIndex)).map((n) => n.id));
}

/** The finding indices shown on a box, for filtering the issue list. */
export function findingsOfBox(view: ViewGraph, boxId: string): number[] {
  return view.nodes.find((n) => n.id === boxId)?.findings ?? [];
}
