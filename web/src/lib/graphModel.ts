// Turns the report's graph into what the map shows: a folder tree in which closed folders are
// single boxes and open folders are containers with their files and sub-folders inside. Folders
// that only contain one sub-folder are merged into it (`src/pkg/`), and edges are merged and counted.

import { plural, worstSeverity } from "./format";
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
export const AUTO_EXPAND_LIMIT = 25; // files; smaller projects open every folder
export const AUTO_EXPAND_BOXES = 14; // larger ones open folders while the map has at most this many boxes

export const folderId = (path: string) => `folder:${path}`;
export const groupId = (path: string) => `group:${path}`;

/** Folders to expand initially: all of them for small projects; for large ones, open the
 * biggest folders level by level while the map stays at a readable number of boxes. */
export function defaultExpanded(graph: ProjectGraph): Set<string> {
  const code = graph.nodes.filter((n) => n.kind === "module" || n.kind === "notebook" || n.kind === "test");
  if (code.length <= AUTO_EXPAND_LIMIT) {
    return new Set(graph.nodes.filter((n) => n.kind === "folder").map((n) => n.id));
  }
  const expanded = new Set<string>();
  const options = { expanded, showTests: true };
  for (;;) {
    const view = buildViewGraph(graph, [], options);
    const closed = view.nodes
      .filter((n) => n.kind === "folder" && n.folder)
      .sort((a, b) => b.members.length - a.members.length);
    let opened = false;
    for (const box of closed) {
      expanded.add(box.folder!);
      if (buildViewGraph(graph, [], options).nodes.length <= AUTO_EXPAND_BOXES) opened = true;
      else expanded.delete(box.folder!);
    }
    if (!opened) return expanded;
  }
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

/** The folder tree of the visible files, with folders that hold nothing visible left out. */
class FolderTree {
  readonly items = new Map<string | null, GraphNode[]>(); // folder (null = root) -> its files
  readonly children = new Map<string | null, string[]>(); // folder -> its sub-folders
  readonly folders: Map<string, GraphNode>;

  constructor(graph: GraphNode[], visible: GraphNode[]) {
    this.folders = new Map(graph.filter((n) => n.kind === "folder").map((n) => [n.id, n]));
    for (const node of visible) {
      const folder = node.parent !== null && CODE_KINDS.has(node.kind) ? node.parent : null;
      this.items.set(folder, [...(this.items.get(folder) ?? []), node]);
    }
    const used = new Set<string>();
    for (const folder of this.items.keys()) {
      for (let path = folder; path !== null && !used.has(path); path = this.folders.get(path)?.parent ?? null) {
        used.add(path);
      }
    }
    for (const path of [...used].sort()) {
      const parent = this.folders.get(path)?.parent ?? null;
      this.children.set(parent, [...(this.children.get(parent) ?? []), path]);
    }
  }

  /** Follow folders that only contain one sub-folder, so ``src/pkg/`` becomes one step. */
  chain(start: string): string[] {
    const chain = [start];
    for (;;) {
      const last = chain[chain.length - 1]!;
      const subs = this.children.get(last) ?? [];
      if ((this.items.get(last) ?? []).length > 0 || subs.length !== 1) return chain;
      chain.push(subs[0]!);
    }
  }

  /** Every file below ``folder`` and every folder path below it (including itself). */
  descendants(folder: string): { files: GraphNode[]; folders: string[] } {
    const files: GraphNode[] = [];
    const folders: string[] = [];
    const walk = (path: string) => {
      folders.push(path);
      files.push(...(this.items.get(path) ?? []));
      for (const sub of this.children.get(path) ?? []) walk(sub);
    };
    walk(folder);
    return { files, folders };
  }
}

export function buildViewGraph(graph: ProjectGraph, findings: Finding[], options: ViewOptions): ViewGraph {
  const degree = new Map<string, number>();
  for (const edge of graph.edges) {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  }
  const visible = graph.nodes.filter(
    (n) => n.kind !== "folder" && !isClutter(n, degree) && (options.showTests || n.kind !== "test"),
  );
  const tree = new FolderTree(graph.nodes, visible);
  const nodes: ViewNode[] = [];
  const unitOf = new Map<string, string>();
  const severityOf = (indices: number[]) => worstSeverity(indices.map((i) => findings[i]?.severity));
  const folderFindings = (paths: string[]) => paths.flatMap((p) => tree.folders.get(p)?.findings ?? []);

  const addFile = (node: GraphNode, parent: string | undefined) => {
    nodes.push({
      id: node.id,
      kind: fileKind(node),
      label: node.label,
      sub: fileSub(node),
      severity: node.worst_severity,
      findings: unique(node.findings),
      members: [node.id],
      parent,
    });
    unitOf.set(node.id, node.id);
  };

  // ``start`` begins a chain of single-sub-folder folders; the chain is drawn as one box,
  // labelled relative to the folder it sits in.
  const addFolder = (start: string, parent: string | undefined, base: string | null) => {
    const chain = tree.chain(start);
    const path = chain[chain.length - 1]!;
    const label = `${base ? path.slice(base.length + 1) : path}/`;
    if (options.expanded.has(path)) {
      const id = groupId(path);
      const own = unique(folderFindings(chain));
      nodes.push({ id, kind: "group", label, sub: "", severity: severityOf(own), findings: own, members: [], folder: path, parent });
      for (const folder of chain) unitOf.set(folder, id);
      for (const file of tree.items.get(path) ?? []) addFile(file, id);
      for (const sub of tree.children.get(path) ?? []) addFolder(sub, id, path);
      return;
    }
    const id = folderId(path);
    const { files, folders } = tree.descendants(path);
    const found = unique([...files.flatMap((f) => f.findings), ...folderFindings([...chain, ...folders])]);
    const lines = files.reduce((sum, f) => sum + f.lines_of_code, 0);
    nodes.push({
      id,
      kind: "folder",
      label,
      sub: `${plural(files.length, "file")} · ${lines} lines`,
      severity: severityOf(found),
      findings: found,
      members: files.map((f) => f.id),
      folder: path,
      parent,
    });
    for (const folder of [...chain, ...folders]) unitOf.set(folder, id);
    for (const file of files) unitOf.set(file.id, id);
  };

  for (const file of tree.items.get(null) ?? []) addFile(file, undefined);
  for (const top of tree.children.get(null) ?? []) addFolder(top, undefined, null);

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

  // Containers must come before their children (React Flow requirement); folders are added
  // depth-first, so a stable sort that moves containers forward keeps parents first.
  const ordered = [...nodes].sort((a, b) => Number(b.kind === "group") - Number(a.kind === "group"));
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
