import { describe, expect, it } from "vitest";

import { formatLocation, splitSteps, worstSeverity } from "./format";
import { boxesForFinding, buildViewGraph, defaultExpanded, findingsOfBox, folderId, groupId } from "./graphModel";
import { highlightPython } from "./highlight";
import { layoutGraph } from "./layout";
import { absoluteLine, blockAtLine, buildBlockView, flaggedLines } from "./blockModel";
import type { Block, FileInfo, Finding, GraphNode, ProjectGraph } from "./types";

function node(partial: Partial<GraphNode> & Pick<GraphNode, "id" | "kind">): GraphNode {
  return {
    label: partial.id.split("/").pop() ?? partial.id,
    parent: null, role: "library", lines_of_code: 10, functions: 1, classes: 0,
    max_complexity: 1, third_party: [], findings: [], worst_severity: null, ...partial,
  };
}

function finding(severity: Finding["severity"], path: string): Finding {
  return {
    check_id: "x", title: "x", severity, dimension: "structure", concept: "c", message: "m",
    locations: [{ path, start_line: 1, end_line: null, cell: null }], evidence: "", explanation: null,
  };
}

const findings = [finding("critical", "pkg/a.py"), finding("minor", "pkg/b.py"), finding("major", ".")];

const graph: ProjectGraph = {
  nodes: [
    node({ id: "pkg", kind: "folder", label: "pkg/" }),
    node({ id: "main.py", kind: "module", role: "entry", findings: [] }),
    node({ id: "pkg/a.py", kind: "module", parent: "pkg", findings: [0], worst_severity: "critical" }),
    node({ id: "pkg/b.py", kind: "module", parent: "pkg", findings: [1], worst_severity: "minor" }),
    node({ id: "pkg/__init__.py", kind: "module", parent: "pkg", label: "__init__.py" }),
    node({ id: "tests/test_a.py", kind: "test", parent: "tests" }),
    node({ id: "tests", kind: "folder" }),
    node({ id: "missing:environment", kind: "missing", label: "environment.yml", findings: [2], worst_severity: "major" }),
  ],
  edges: [
    { source: "main.py", target: "pkg/a.py", kind: "import", names: [], line: 1 },
    { source: "main.py", target: "pkg/b.py", kind: "import", names: [], line: 2 },
    { source: "pkg/a.py", target: "pkg/b.py", kind: "import", names: [], line: 1 },
    { source: "tests/test_a.py", target: "pkg/a.py", kind: "test", names: [], line: 1 },
  ],
  project_findings: [],
  unresolved_imports: [],
};

describe("buildViewGraph", () => {
  it("collapses folders into one box and merges their edges", () => {
    const view = buildViewGraph(graph, findings, { expanded: new Set(), showTests: true });
    const pkg = view.nodes.find((n) => n.id === folderId("pkg"))!;

    expect(pkg.members.sort()).toEqual(["pkg/a.py", "pkg/b.py"]); // empty __init__ is hidden
    expect(pkg.severity).toBe("critical");
    expect(pkg.findings).toEqual([0, 1]);
    const fromMain = view.edges.find((e) => e.source === "main.py")!;
    expect(fromMain).toMatchObject({ target: folderId("pkg"), count: 2 });
    expect(view.edges.some((e) => e.source === folderId("pkg") && e.target === folderId("pkg"))).toBe(false);
  });

  it("shows files inside a container when a folder is expanded", () => {
    const view = buildViewGraph(graph, findings, { expanded: new Set(["pkg"]), showTests: true });

    expect(view.nodes[0]!.kind).toBe("group"); // containers come first
    expect(view.nodes.find((n) => n.id === "pkg/a.py")!.parent).toBe(groupId("pkg"));
    expect(view.edges.find((e) => e.source === "pkg/a.py")!.target).toBe("pkg/b.py");
  });

  it("can hide tests", () => {
    const view = buildViewGraph(graph, findings, { expanded: new Set(), showTests: false });

    expect(view.nodes.some((n) => n.id.includes("tests"))).toBe(false);
  });

  it("links findings and boxes both ways", () => {
    const view = buildViewGraph(graph, findings, { expanded: new Set(), showTests: true });

    expect([...boxesForFinding(view, 0)]).toEqual([folderId("pkg")]);
    expect([...boxesForFinding(view, 2)]).toEqual(["missing:environment"]);
    expect(findingsOfBox(view, folderId("pkg"))).toEqual([0, 1]);
  });

  it("expands everything for small projects", () => {
    expect([...defaultExpanded(graph)].sort()).toEqual(["pkg", "tests"]);
  });
});

describe("layoutGraph", () => {
  it("positions every box, with children inside their container", async () => {
    const view = buildViewGraph(graph, findings, { expanded: new Set(["pkg"]), showTests: true });

    const { positions } = await layoutGraph(view);

    for (const n of view.nodes) expect(positions.has(n.id)).toBe(true);
    const group = positions.get(groupId("pkg"))!;
    const child = positions.get("pkg/a.py")!;
    expect(child.x + child.width).toBeLessThanOrEqual(group.width);
  });

  it("routes edges in absolute coordinates, from box border to box border", async () => {
    const view = buildViewGraph(graph, findings, { expanded: new Set(["pkg"]), showTests: true });

    const { positions, routes } = await layoutGraph(view);

    type Box = { x: number; y: number; width: number; height: number };
    const absolute = (id: string): Box => {
      const box = positions.get(id)!;
      const parent = view.nodes.find((n) => n.id === id)!.parent;
      const offset = parent ? absolute(parent) : { x: 0, y: 0 };
      return { x: box.x + offset.x, y: box.y + offset.y, width: box.width, height: box.height };
    };
    const touches = (p: { x: number; y: number }, id: string) => {
      const b = absolute(id);
      return p.x >= b.x - 1 && p.x <= b.x + b.width + 1 && p.y >= b.y - 1 && p.y <= b.y + b.height + 1;
    };
    expect(routes.size).toBe(view.edges.length);
    for (const edge of view.edges) {
      const route = routes.get(edge.id)!;
      expect(touches(route[0]!, edge.source)).toBe(true);
      expect(touches(route[route.length - 1]!, edge.target)).toBe(true);
    }
  });
});

describe("folder tree", () => {
  const deep: ProjectGraph = {
    nodes: [
      node({ id: "app", kind: "folder" }),
      node({ id: "app/src", kind: "folder", parent: "app" }),
      node({ id: "app/src/pkg", kind: "folder", parent: "app/src" }),
      node({ id: "app/src/pkg/core.py", kind: "module", parent: "app/src/pkg" }),
      node({ id: "app/src/pkg/io.py", kind: "module", parent: "app/src/pkg" }),
      node({ id: "app/tests", kind: "folder", parent: "app" }),
      node({ id: "app/tests/test_core.py", kind: "test", parent: "app/tests" }),
      node({ id: "app/pyproject.toml", kind: "config", parent: "app" }),
    ],
    edges: [{ source: "app/tests/test_core.py", target: "app/src/pkg/core.py", kind: "test", names: [], line: 1 }],
    project_findings: [],
    unresolved_imports: [],
  };

  it("nests sub-folders inside an open folder and merges single-child chains", () => {
    const view = buildViewGraph(deep, [], { expanded: new Set(["app"]), showTests: true });

    const pkg = view.nodes.find((n) => n.id === folderId("app/src/pkg"))!;
    expect(pkg.label).toBe("src/pkg/"); // app/src only holds pkg, so it is one step
    expect(pkg.parent).toBe(groupId("app"));
    expect(view.nodes.find((n) => n.id === "app/pyproject.toml")!.parent).toBe(groupId("app"));
    expect(view.nodes.some((n) => n.id.includes("app/src") && n.id !== pkg.id)).toBe(false);
    expect(view.edges).toEqual([
      expect.objectContaining({ source: folderId("app/tests"), target: folderId("app/src/pkg") }),
    ]);
  });

  it("counts every file below a closed folder", () => {
    const view = buildViewGraph(deep, [], { expanded: new Set(), showTests: true });

    expect(view.nodes.map((n) => n.id)).toEqual([folderId("app")]);
    expect(view.nodes[0]!.members).toHaveLength(4);
  });
});

describe("helpers", () => {
  it("highlights Python tokens", () => {
    const kinds = highlightPython('x = load("a.csv")  # read').map((t) => t.kind);

    expect(kinds).toContain("fn");
    expect(kinds).toContain("str");
    expect(kinds).toContain("com");
    expect(highlightPython("from os import path")[0]).toEqual({ text: "from", kind: "kw" });
  });

  it("splits numbered steps", () => {
    expect(splitSteps("1. Add x. 2. Remove y. 3. Run it.")).toEqual(["Add x.", "Remove y.", "Run it."]);
    expect(splitSteps("Just do it.")).toEqual(["Just do it."]);
  });

  it("formats locations and picks the worst severity", () => {
    expect(formatLocation({ path: "a.py", start_line: 3, end_line: null, cell: 2 })).toBe("a.py [cell 2]:3");
    expect(formatLocation({ path: ".", start_line: null, end_line: null, cell: null })).toBe("whole project");
    expect(worstSeverity(["minor", null, "major"])).toBe("major");
  });
});

describe("block model", () => {
  const block = (partial: Partial<Block> & Pick<Block, "id" | "name" | "kind">): Block => ({
    path: "m.py", parent: null, start_line: 1, end_line: 1, lines_of_code: 1, complexity: 1,
    has_docstring: false, calls: [], findings: [], ...partial,
  });
  const info: FileInfo = {
    sha256: "x",
    lines: 30,
    cell_starts: [],
    blocks: [
      block({ id: "m.py::Model", name: "Model", kind: "class", start_line: 1, end_line: 12 }),
      block({ id: "m.py::Model.fit", name: "Model.fit", kind: "method", parent: "m.py::Model", start_line: 3, end_line: 8, calls: ["m.py::Model", "m.py::helper"], findings: [0] }),
      block({ id: "m.py::helper", name: "helper", kind: "function", start_line: 14, end_line: 20 }),
      block({ id: "m.py::module code", name: "module code", kind: "module", start_line: 1, end_line: 30, lines_of_code: 0 }),
    ],
  };
  const fileFindings = [finding("major", "m.py")];

  it("draws classes as containers, skips empty module code and nesting edges", () => {
    const view = buildBlockView(info, fileFindings);

    expect(view.nodes.map((n) => n.id)).toEqual(["m.py::Model", "m.py::Model.fit", "m.py::helper"]);
    expect(view.nodes[0]!.kind).toBe("group");
    expect(view.nodes[1]).toMatchObject({ label: "fit", parent: "m.py::Model", severity: "major" });
    expect(view.edges.map((e) => [e.source, e.target])).toEqual([["m.py::Model.fit", "m.py::helper"]]);
  });

  it("finds the innermost block of a line", () => {
    expect(blockAtLine(info, 5)!.id).toBe("m.py::Model.fit");
    expect(blockAtLine(info, 13)!.kind).toBe("module");
  });

  it("translates notebook cell lines and collects flagged lines", () => {
    const nb: FileInfo = { ...info, cell_starts: [1, 6, 10] };
    const location = { path: "nb.ipynb", start_line: 2, end_line: null, cell: 3 };

    expect(absoluteLine(location, nb)).toBe(11);
    const flagged = flaggedLines([{ ...fileFindings[0]!, locations: [location] }], "nb.ipynb", nb);
    expect([...flagged.entries()]).toEqual([[11, [0]]]);
  });
});
