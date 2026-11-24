// Positions boxes with ELK's layered algorithm (dependencies flow in one direction, like a
// pipeline). Expanded folders are laid out as nested containers. Both directions are tried and
// the one that fills the map area best wins, so wide projects don't shrink to unreadable.

import ELK, { type ElkNode } from "elkjs/lib/elk.bundled.js";

import type { ViewGraph, ViewNode } from "./graphModel";

const elk = new ELK();
const CHAR_MONO = 7.6; // px per character at 12.5px JetBrains Mono
const CHAR_SMALL = 6.2;
export const NODE_HEIGHT = 46;

export type Direction = "RIGHT" | "DOWN";

export interface Positioned {
  id: string;
  x: number; // relative to the parent container if there is one
  y: number;
  width: number;
  height: number;
}

export interface Layout {
  positions: Map<string, Positioned>;
  width: number;
  height: number;
  direction: Direction;
}

export function nodeWidth(node: ViewNode): number {
  const text = Math.max(node.label.length * CHAR_MONO, node.sub.length * CHAR_SMALL);
  return Math.round(Math.min(Math.max(text + 30, 128), 340));
}

function elkGraph(view: ViewGraph, direction: Direction): ElkNode {
  const elkNodes = new Map<string, ElkNode>();
  const roots: ElkNode[] = [];
  for (const node of view.nodes) {
    elkNodes.set(
      node.id,
      node.kind === "group"
        ? { id: node.id, children: [], layoutOptions: { "elk.padding": "[top=38,left=16,bottom=16,right=16]" } }
        : { id: node.id, width: nodeWidth(node), height: NODE_HEIGHT },
    );
  }
  for (const node of view.nodes) {
    const elkNode = elkNodes.get(node.id)!;
    const parent = node.parent ? elkNodes.get(node.parent) : undefined;
    if (parent) parent.children!.push(elkNode);
    else roots.push(elkNode);
  }
  return {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": direction,
      "elk.hierarchyHandling": "INCLUDE_CHILDREN",
      "elk.spacing.nodeNode": direction === "RIGHT" ? "22" : "28",
      "elk.layered.spacing.nodeNodeBetweenLayers": direction === "RIGHT" ? "70" : "56",
      "elk.spacing.componentComponent": "40",
      "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
    },
    children: roots,
    edges: view.edges.map((e) => ({ id: e.id, sources: [e.source], targets: [e.target] })),
  };
}

async function layoutIn(view: ViewGraph, direction: Direction): Promise<Layout> {
  const result = await elk.layout(elkGraph(view, direction));
  const positions = new Map<string, Positioned>();
  const walk = (children: ElkNode[] | undefined) => {
    for (const child of children ?? []) {
      positions.set(child.id, {
        id: child.id, x: child.x ?? 0, y: child.y ?? 0, width: child.width ?? 0, height: child.height ?? 0,
      });
      walk(child.children);
    }
  };
  walk(result.children);
  return { positions, width: result.width ?? 0, height: result.height ?? 0, direction };
}

/** How large the drawing appears when fitted into a ``width`` x ``height`` area. */
export function fitScale(layout: Layout, width: number, height: number): number {
  if (!layout.width || !layout.height) return 1;
  return Math.min(width / layout.width, height / layout.height);
}

/** Lay out in both directions and keep the one that will look biggest in the given area. */
export async function layoutGraph(view: ViewGraph, area?: { width: number; height: number }): Promise<Layout> {
  const right = await layoutIn(view, "RIGHT");
  if (!area || !area.width || !area.height) return right;
  const down = await layoutIn(view, "DOWN");
  // Prefer left-to-right unless top-to-bottom is clearly more readable.
  return fitScale(down, area.width, area.height) > fitScale(right, area.width, area.height) * 1.15 ? down : right;
}
