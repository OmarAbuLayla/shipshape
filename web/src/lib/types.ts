// Mirrors engine/src/shipshape/models.py (report schema 0.4) and the API's scan summary.

export type Severity = "critical" | "major" | "minor";
export type Dimension =
  | "correctness"
  | "structure"
  | "reproducibility"
  | "readability"
  | "testing"
  | "security";
export type FixStatus = "verified" | "rejected" | "none";
export type NodeKind =
  | "module"
  | "notebook"
  | "test"
  | "folder"
  | "config"
  | "external"
  | "missing";
export type EdgeKind = "import" | "test" | "reads";

export interface Location {
  path: string;
  start_line: number | null;
  end_line: number | null;
  cell: number | null;
}

export interface Edit {
  path: string;
  search: string;
  replace: string;
}

export interface Explanation {
  summary: string;
  what: string;
  why: string;
  how_to_fix: string;
  behaviour_change: string;
  edits: Edit[];
  fix_status: FixStatus;
  fix_note: string;
  model: string;
  cached: boolean;
}

export interface Finding {
  check_id: string;
  title: string;
  severity: Severity;
  dimension: Dimension;
  concept: string;
  message: string;
  locations: Location[];
  evidence: string;
  explanation: Explanation | null;
}

export interface GraphNode {
  id: string;
  kind: NodeKind;
  label: string;
  parent: string | null;
  role: string;
  lines_of_code: number;
  functions: number;
  classes: number;
  max_complexity: number;
  third_party: string[];
  findings: number[];
  worst_severity: Severity | null;
}

export interface GraphEdge {
  source: string;
  target: string;
  kind: EdgeKind;
  names: string[];
  line: number | null;
}

export interface ProjectGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  project_findings: number[];
  unresolved_imports: string[];
}

export interface ExplainStats {
  provider: string;
  model: string;
  findings_explained: number;
  api_calls: number;
  retries: number;
  cache_hits: number;
  failures: number;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number | null;
  fixes_verified: number;
  fixes_rejected: number;
  seconds: number;
}

export interface Report {
  schema_version: string;
  engine_version: string;
  project_name: string;
  stats: { python_files: number; notebooks: number; lines_of_code: number };
  files_scanned: string[];
  findings: Finding[];
  scores: Partial<Record<Dimension, number>>;
  grade: string;
  check_errors: string[];
  graph: ProjectGraph | null;
  explain_stats: ExplainStats | null;
}

export type ScanStatus = "queued" | "running" | "done" | "failed";

export interface ScanSummary {
  id: string;
  name: string;
  source: "path" | "upload";
  explain: boolean;
  status: ScanStatus;
  progress: string;
  error: string;
  created_at: string;
  finished_at: string | null;
  grade: string | null;
  findings: number | null;
}

export interface Health {
  status: string;
  api_version: string;
  engine_version: string;
  llm: { configured: boolean; provider: string | null; model: string | null; problem: string | null };
}

export const DIMENSIONS: Dimension[] = [
  "correctness",
  "structure",
  "reproducibility",
  "readability",
  "testing",
  "security",
];
export const SEVERITIES: Severity[] = ["critical", "major", "minor"];
