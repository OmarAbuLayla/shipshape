import type { Location, Severity } from "./types";

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
  if (location.cell !== null) text += ` [cell ${location.cell}]`;
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

const PROVIDER_NAMES: Record<string, string> = { deepseek: "DeepSeek", openai: "OpenAI", anthropic: "Anthropic" };

export function providerName(provider: string | null | undefined): string {
  return provider ? (PROVIDER_NAMES[provider] ?? capitalize(provider)) : "the AI provider";
}

export function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
