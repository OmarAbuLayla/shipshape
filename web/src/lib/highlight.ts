// A small Python highlighter for diff lines. Good enough for short snippets, no dependency.

export type Token = { text: string; kind: "kw" | "str" | "com" | "num" | "fn" | "plain" };

const KEYWORDS = new Set(
  (
    "False None True and as assert async await break class continue def del elif else except " +
    "finally for from global if import in is lambda nonlocal not or pass raise return try while " +
    "with yield"
  ).split(" "),
);

const PATTERN =
  /(#.*$)|((?:[rbfRBF]{1,2})?(?:"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'))|(\b\d[\d_]*(?:\.\d+)?(?:e[+-]?\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)(?=\s*\()|([A-Za-z_][A-Za-z0-9_]*)/g;

export function highlightPython(line: string): Token[] {
  const tokens: Token[] = [];
  let last = 0;
  for (const match of line.matchAll(PATTERN)) {
    const index = match.index ?? 0;
    if (index > last) tokens.push({ text: line.slice(last, index), kind: "plain" });
    const [whole, comment, string, number, call, word] = match;
    if (comment) tokens.push({ text: whole, kind: "com" });
    else if (string) tokens.push({ text: whole, kind: "str" });
    else if (number) tokens.push({ text: whole, kind: "num" });
    else if (call) tokens.push({ text: whole, kind: KEYWORDS.has(call) ? "kw" : "fn" });
    else if (word) tokens.push({ text: whole, kind: KEYWORDS.has(word) ? "kw" : "plain" });
    last = index + whole.length;
  }
  if (last < line.length) tokens.push({ text: line.slice(last), kind: "plain" });
  return tokens;
}
