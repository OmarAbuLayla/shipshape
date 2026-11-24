import type { Exclusions, Location, Severity } from "./types";

const SEVERITY_RANK: Record<Severity, number> = { critical: 0, major: 1, minor: 2 };

export function worstSeverity(values: (Severity | null | undefined)[]): Severity | null {
  let best: Severity | null = null;
  for (const value of values) {
    if (value && (best === null || SEVERITY_RANK[value] < SEVERITY_RANK[best])) best = value;
  }
  return best;
}

export function formatLocation(location: Location): string {
  if (location.path === ".") return "whole project";
  let text = location.path;
  if (location.cell !== null) text += ` [code cell ${location.cell}]`;
  if (location.start_line !== null) text += `:${location.start_line}`;
  return text;
}

export function formatWhen(iso: string): string {
  const date = new Date(iso);
  const seconds = (Date.now() - date.getTime()) / 1000;
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function plural(count: number, word: string, many = `${word}s`): string {
  return `${count} ${count === 1 ? word : many}`;
}

/** Split "1. Do this. 2. Then that." (or one step per line) into steps. */
export function splitSteps(text: string): string[] {
  const parts = text
    .split(/(?:^|\s)(?=\d+[.)]\s)/)
    .map((part) => part.replace(/^\d+[.)]\s*/, "").trim())
    .filter(Boolean);
  return parts.length > 1 ? parts : [text.trim()];
}

export function scoreColor(score: number): string {
  if (score >= 75) return "var(--ok)";
  if (score >= 50) return "var(--major)";
  return "var(--crit)";
}

const PROVIDER_NAMES: Record<string, string> = {
  deepseek: "DeepSeek",
  openai: "OpenAI",
  anthropic: "Anthropic",
  "openai-compatible": "your configured AI service",
};

export function providerName(provider: string | null | undefined): string {
  return provider ? (PROVIDER_NAMES[provider] ?? capitalize(provider)) : "the AI provider";
}

export function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Keep the last ``keep`` path segments, e.g. ".../discovery/curation.py", for tight spaces. */
export function shortPath(path: string, keep = 2): string {
  const parts = path.split("/");
  return parts.length > keep + 1 ? `…/${parts.slice(-keep).join("/")}` : path;
}

/** One sentence per kind of exclusion (mirrors the engine's ``describe_exclusions``). */
export function exclusionLines(ex: Exclusions | undefined): string[] {
  if (!ex) return [];
  const lines: string[] = [];
  if (ex.files_excluded) {
    const shown = ex.patterns.slice(0, 6).join(", ") + (ex.patterns.length > 6 ? ", ..." : "");
    lines.push(`${plural(ex.files_excluded, "file")} left out by .shipshapeignore (${shown}).`);
  }
  if (ex.disabled_checks.length) lines.push(`Checks switched off: ${ex.disabled_checks.join(", ")}.`);
  const inline = new Map<string, number>();
  for (const s of ex.suppressed) {
    if (s.how === "inline comment") inline.set(s.check_id, (inline.get(s.check_id) ?? 0) + 1);
  }
  if (inline.size) {
    const total = [...inline.values()].reduce((a, b) => a + b, 0);
    const ids = [...inline.entries()].map(([id, n]) => `${id} (${n})`).join(", ");
    lines.push(`${plural(total, "place")} marked "# shipshape: ignore" in the code: ${ids}.`);
  }
  return lines;
}
