import {
  Background,
  BackgroundVariant,
  BaseEdge,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { memo, useEffect, useMemo, useRef, useState, type RefObject } from "react";

import type { ViewGraph, ViewNode } from "../lib/graphModel";
import { layoutGraph, NODE_HEIGHT, nodeWidth, type Layout, type Point } from "../lib/layout";

interface BoxData extends Record<string, unknown> {
  view: ViewNode;
  highlighted: boolean;
  dimmed: boolean;
  selected: boolean;
  vertical: boolean;
  onToggleFolder: (folder: string) => void;
}

const BoxNode = memo(function BoxNode({ data }: NodeProps<Node<BoxData>>) {
  const { view, highlighted, dimmed, selected, vertical } = data;
  const classes = ["node", view.kind, view.severity ?? "", highlighted ? "highlight" : "", dimmed ? "dim" : "", selected ? "selected" : ""];
  if (view.kind === "folder") classes.push("collapsed");
  return (
    <div className={classes.join(" ")} style={{ width: nodeWidth(view), height: NODE_HEIGHT }}>
      <Handle type="target" position={vertical ? Position.Top : Position.Left} />
      <div className="n">{view.label}</div>
      <div className="s">{view.sub}</div>
      {view.findings.length > 0 && view.severity && <span className={`badge ${view.severity}`}>{view.findings.length}</span>}
      {view.kind === "folder" && view.folder && (
        <button
          className="expand"
          style={{ position: "absolute", right: 4, bottom: 2, border: 0, background: "none", cursor: "pointer", padding: "4px 6px" }}
          onClick={(e) => {
            e.stopPropagation();
            data.onToggleFolder(view.folder!);
          }}
          aria-label={`Open folder ${view.label}`}
        >
          open ▸
        </button>
      )}
      <Handle type="source" position={vertical ? Position.Bottom : Position.Right} />
    </div>
  );
});

const GroupNode = memo(function GroupNode({ data }: NodeProps<Node<BoxData>>) {
  const { view, highlighted } = data;
  return (
    <div className={`group-node ${highlighted ? "highlight" : ""}`}>
      <div className="gl">
        {view.label}
        {view.folder && (
          <button
            style={{ border: 0, background: "none", cursor: "pointer", padding: 0, font: "inherit" }}
            onClick={(e) => {
              e.stopPropagation();
              data.onToggleFolder(view.folder!);
            }}
            aria-label={`Close folder ${view.label}`}
          >
            <em>close ▾</em>
          </button>
        )}
      </div>
    </div>
  );
});

const nodeTypes = { box: BoxNode, group: GroupNode };

interface RoutedData extends Record<string, unknown> {
  points: Point[] | null; // ELK's route; null falls back to a straight line
  count: number;
}

/** An SVG path through ``points`` with small rounded corners at each bend. */
export function roundedPath(points: Point[], radius = 7): string {
  const [first, ...rest] = points;
  if (!first) return "";
  let path = `M ${first.x} ${first.y}`;
  for (let i = 0; i < rest.length; i++) {
    const corner = rest[i]!;
    const next = rest[i + 1];
    const prev = i === 0 ? first : rest[i - 1]!;
    if (!next) {
      path += ` L ${corner.x} ${corner.y}`;
      break;
    }
    const r = Math.min(radius, Math.hypot(corner.x - prev.x, corner.y - prev.y) / 2, Math.hypot(next.x - corner.x, next.y - corner.y) / 2);
    const towards = (from: Point, to: Point, d: number) => {
      const length = Math.hypot(to.x - from.x, to.y - from.y) || 1;
      return { x: from.x + ((to.x - from.x) / length) * d, y: from.y + ((to.y - from.y) / length) * d };
    };
    const before = towards(corner, prev, r);
    const after = towards(corner, next, r);
    path += ` L ${before.x} ${before.y} Q ${corner.x} ${corner.y} ${after.x} ${after.y}`;
  }
  return path;
}

/** Middle of the route's longest straight piece: the calmest place for a count label. */
export function labelPoint(points: Point[]): Point {
  let best = { x: points[0]?.x ?? 0, y: points[0]?.y ?? 0 };
  let longest = -1;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1]!;
    const b = points[i]!;
    const length = Math.hypot(b.x - a.x, b.y - a.y);
    if (length > longest) {
      longest = length;
      best = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    }
  }
  return best;
}

const RoutedEdge = memo(function RoutedEdge(props: EdgeProps<Edge<RoutedData>>) {
  const { sourceX, sourceY, targetX, targetY, data, style, markerEnd } = props;
  const points = data?.points ?? [
    { x: sourceX, y: sourceY },
    { x: targetX, y: targetY },
  ];
  const label = labelPoint(points);
  return (
    <BaseEdge
      path={roundedPath(points)}
      style={style}
      markerEnd={markerEnd}
      label={data && data.count > 1 ? String(data.count) : undefined}
      labelX={label.x}
      labelY={label.y}
      labelBgPadding={[3, 1]}
      labelBgBorderRadius={3}
    />
  );
});

const edgeTypes = { routed: RoutedEdge };

/** Above this many lines the map draws them faintly and brings out the lines of one box. */
const BUSY_EDGES = 30;

const EDGE_COLOR = { import: "var(--faint)", test: "var(--ok)", reads: "var(--major)" } as const;

/** Ask the map to pan to a box; ``request`` changes on every click so repeats still work. */
export interface FocusRequest {
  id: string;
  request: number;
}

interface Props {
  view: ViewGraph;
  highlighted: Set<string>;
  selectedBox: string | null;
  onSelectBox: (id: string | null) => void;
  onToggleFolder: (folder: string) => void;
  focus: FocusRequest | null; // box to pan to (e.g. after clicking a location)
  onOpenBox?: (id: string) => void; // double-click on a box that is not a folder
  legend?: "map" | "blocks";
}

function MapInner({ view, highlighted, selectedBox, onSelectBox, onToggleFolder, focus, area, onOpenBox }: Props & {
  area: RefObject<HTMLDivElement>;
}) {
  const [layout, setLayout] = useState<Layout | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const flow = useReactFlow();

  useEffect(() => {
    let alive = true;
    const size = area.current ? { width: area.current.clientWidth, height: area.current.clientHeight } : undefined;
    layoutGraph(view, size).then((result) => alive && setLayout(result));
    return () => {
      alive = false;
    };
  }, [view, area]);

  useEffect(() => {
    // Centre the map after each new layout. React Flow only fits once it has measured the
    // boxes in the DOM, which can take a moment (longer in background tabs), so retry briefly.
    if (!layout) return;
    let alive = true;
    let timer: number | undefined;
    const attempt = async (left: number) => {
      // Never shrink below 60%: text stays readable and the rest is one drag away.
      const ok = await flow.fitView({ padding: 0.1, maxZoom: 1.1, minZoom: 0.6 });
      if (alive && !ok && left > 0) timer = window.setTimeout(() => void attempt(left - 1), 100);
    };
    timer = window.setTimeout(() => void attempt(30), 20);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [layout, flow]);

  // When an issue is selected, bring its boxes into view (they may be off-screen).
  useEffect(() => {
    if (!layout || highlighted.size === 0) return;
    const ids = [...highlighted].filter((id) => flow.getNode(id));
    if (ids.length === 0) return;
    void flow.fitView({ nodes: ids.map((id) => ({ id })), padding: 0.5, maxZoom: 1.1, minZoom: 0.6, duration: 300 });
  }, [highlighted, layout, flow]);

  useEffect(() => {
    if (!focus || !layout) return;
    if (flow.getNode(focus.id)) {
      void flow.fitView({ nodes: [{ id: focus.id }], padding: 0.8, maxZoom: 1.2, duration: 300 });
    }
  }, [focus, layout, flow]);

  const nodes = useMemo<Node<BoxData>[]>(() => {
    if (!layout) return [];
    const anyHighlight = highlighted.size > 0;
    const vertical = layout.direction === "DOWN";
    return view.nodes.flatMap((v) => {
      const p = layout.positions.get(v.id);
      if (!p) return [];
      const isGroup = v.kind === "group";
      return [{
        id: v.id,
        type: isGroup ? "group" : "box",
        position: { x: p.x, y: p.y },
        // ELK already knows every size; giving it to React Flow lets fitView work without
        // waiting for DOM measurement (which a controlled flow does not store back).
        width: p.width,
        height: p.height,
        parentId: v.parent,
        extent: v.parent ? ("parent" as const) : undefined,
        draggable: false,
        selectable: false,
        // Open folders at the back, then lines, then boxes on top, so lines never cover names.
        zIndex: isGroup ? 0 : 3,
        style: isGroup ? { width: p.width, height: p.height } : undefined,
        data: {
          view: v,
          highlighted: highlighted.has(v.id),
          dimmed: anyHighlight && !isGroup && !highlighted.has(v.id),
          selected: selectedBox === v.id,
          vertical,
          onToggleFolder,
        },
      }];
    });
  }, [layout, view, highlighted, selectedBox, onToggleFolder]);

  const edges = useMemo<Edge<RoutedData>[]>(() => {
    // Lines of the hovered or selected box (or of the selected issue's boxes) stand out; in
    // busy maps every other line is faint, so the structure stays visible without the tangle.
    const focus = new Set(highlighted);
    for (const id of [hovered, selectedBox]) if (id) focus.add(id);
    const busy = view.edges.length > BUSY_EDGES;
    return view.edges.map((e) => {
      const inFocus = focus.has(e.source) || focus.has(e.target);
      const faint = focus.size > 0 ? !inFocus : busy;
      return {
        id: e.id,
        type: "routed",
        source: e.source,
        target: e.target,
        data: { points: layout?.routes.get(e.id) ?? null, count: faint && busy ? 1 : e.count },
        style: {
          stroke: EDGE_COLOR[e.kind],
          strokeWidth: 1.2 + Math.min(Math.log2(e.count), 3) * 0.8,
          strokeDasharray: e.kind === "test" ? "5 4" : e.kind === "reads" ? "2 4" : undefined,
          opacity: faint ? (busy ? 0.18 : 0.25) : 0.9,
        },
        // Fixed size in pixels: thick lines show weight without giant arrowheads.
        markerEnd: { type: MarkerType.ArrowClosed, color: EDGE_COLOR[e.kind], width: 12, height: 12, markerUnits: "userSpaceOnUse" },
        zIndex: inFocus ? 2.5 : 2,
      };
    });
  }, [view, highlighted, hovered, selectedBox, layout]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodeClick={(_, node) => node.type === "box" && onSelectBox(node.id)}
      onNodeDoubleClick={(_, node) => {
        const folder = (node.data as BoxData).view.folder;
        if (folder) onToggleFolder(folder);
        else if (node.type === "box") onOpenBox?.(node.id);
      }}
      zoomOnDoubleClick={false}
      onPaneClick={() => onSelectBox(null)}
      onNodeMouseEnter={(_, node) => node.type === "box" && setHovered(node.id)}
      onNodeMouseLeave={() => setHovered(null)}
      nodesConnectable={false}
      minZoom={0.15}
      maxZoom={2}
      proOptions={{ hideAttribution: true }}
    >
      <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="var(--line)" />
      <Controls showInteractive={false} position="bottom-right" />
    </ReactFlow>
  );
}

export function MapView(props: Props) {
  const area = useRef<HTMLDivElement>(null);
  return (
    <div className="col map-col" aria-label="Architecture map" ref={area}>
      <ReactFlowProvider>
        <MapInner {...props} area={area} />
      </ReactFlowProvider>
      <div className="legend" aria-hidden>
        <span><i style={{ background: "var(--crit-soft)", border: "2px solid var(--crit)" }} />critical</span>
        <span><i style={{ background: "var(--major-soft)", border: "1px solid var(--major)" }} />major</span>
        <span><i style={{ background: "var(--minor-soft)", border: "1.5px dotted var(--minor)" }} />minor</span>
        {props.legend === "blocks" ? (
          <>
            <span style={{ color: "var(--faint)" }}>→ calls (matched by name)</span>
            <span className="faint">double-click a block for its code</span>
          </>
        ) : (
          <>
            <span><i style={{ border: "1px dashed var(--major)" }} />missing</span>
            <span style={{ color: "var(--faint)" }}>→ imports</span>
            <span style={{ color: "var(--ok)" }}>⇢ tests</span>
            <span style={{ color: "var(--major)" }}>⋯ reads data</span>
          </>
        )}
      </div>
    </div>
  );
}
