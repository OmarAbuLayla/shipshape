// Mirrors engine/src/shipshape/models.py (report schema 0.6) and the API's scan summary.

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

export interface Suppression {
  check_id: string;
  title: string;
  location: Location;
  how: string;
}

export interface Exclusions {
  ignore_files: string[];
  patterns: string[];
  files_excluded: number;
  disabled_checks: string[];
  suppressed: Suppression[];
}

export type BlockKind = "function" | "method" | "class" | "cell" | "module";

/** A function, class, method or notebook cell, anchored to lines of the scanned text. */
export interface Block {
  id: string;
  path: string;
  name: string;
  kind: BlockKind;
  parent: string | null;
  start_line: number;
  end_line: number;
  lines_of_code: number;
  complexity: number;
  has_docstring: boolean;
  calls: string[];
  findings: number[];
}

export interface FileInfo {
  sha256: string;
  lines: number;
  cell_starts: number[]; // notebooks: first scanned line of each code cell
  blocks: Block[];
}

/** GET /api/scans/{id}/source */
export interface SourceText {
  path: string;
  text: string;
  cell_starts: number[];
  changed: boolean;
}

/** GET /api/lessons (body empty) and /api/lessons/{name}. */
export interface Lesson {
  slug: string;
  concept: string;
  summary: string;
  checks: string[];
  body: string; // Markdown
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
  /** Missing in reports saved before schema 0.5. */
  exclusions?: Exclusions;
  /** Missing in reports saved before schema 0.6. */
  files?: Record<string, FileInfo>;
}

export interface FixOutcome {
  finding: number;
  check_id: string;
  title: string;
  applied: boolean;
  reason: string;
}

export interface CheckDelta {
  check_id: string;
  title: string;
  before: number;
  after: number;
}

/** Mirrors the API's FixRunResponse. */
export interface FixRun {
  outcomes: FixOutcome[];
  changed_files: string[];
  before_grade: string;
  after_grade: string;
  before_scores: Partial<Record<Dimension, number>>;
  after_scores: Partial<Record<Dimension, number>>;
  deltas: CheckDelta[];
  patch: string;
  zip_available: boolean;
  zip_note: string;
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
