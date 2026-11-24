// A small Markdown renderer for Shipshape's own lessons: headings, paragraphs, lists, fenced
// code (Python highlighted), and inline code, bold, italics and links. It builds React elements
// directly (no HTML strings), so nothing in a lesson can inject markup. Not a general parser.

import type { ReactNode } from "react";

import { highlightPython } from "./highlight";

const INLINE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(\[[^\]]+\]\([^)]+\))/g;

export function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const index = match.index ?? 0;
    if (index > last) out.push(text.slice(last, index));
    const [whole, code, bold, italic, link] = match;
    const key = `${index}`;
    if (code) out.push(<code key={key}>{whole.slice(1, -1)}</code>);
    else if (bold) out.push(<strong key={key}>{whole.slice(2, -2)}</strong>);
    else if (italic) out.push(<em key={key}>{whole.slice(1, -1)}</em>);
    else if (link) {
      const [, label = "", url = ""] = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(whole) ?? [];
      out.push(
        url.startsWith("https://") ? (
          <a key={key} href={url} target="_blank" rel="noopener noreferrer">{label}</a>
        ) : (
          label
        ),
      );
    }
    last = index + whole.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function CodeBlock({ language, code }: { language: string; code: string }) {
  return (
    <pre className={`md-code ${language}`}>
      {code.split("\n").map((line, i) => (
        <span key={i} className="md-line">
          {language === "python"
            ? highlightPython(line).map((token, k) =>
                token.kind === "plain" ? token.text : <span key={k} className={`tok-${token.kind}`}>{token.text}</span>,
              )
            : line}
          {"\n"}
        </span>
      ))}
    </pre>
  );
}

/** Render a lesson body. Headings start at level 2 (the page supplies the title). */
export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  const lines = text.split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i]!;
    const key = `b${i}`;
    if (line.startsWith("```")) {
      const language = line.slice(3).trim();
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i]!.startsWith("```")) body.push(lines[i++]!);
      blocks.push(<CodeBlock key={key} language={language} code={body.join("\n")} />);
      i += 1;
    } else if (/^#{1,3} /.test(line)) {
      const level = line.indexOf(" ");
      const content = inline(line.slice(level + 1));
      blocks.push(level <= 2 ? <h3 key={key}>{content}</h3> : <h4 key={key}>{content}</h4>);
      i += 1;
    } else if (/^[-*] /.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*] /.test(lines[i]!)) items.push(lines[i++]!.slice(2));
      blocks.push(<ul key={key}>{items.map((item, k) => <li key={k}>{inline(item)}</li>)}</ul>);
    } else if (line.trim() === "") {
      i += 1;
    } else {
      const para: string[] = [];
      while (i < lines.length && lines[i]!.trim() !== "" && !/^(```|#{1,3} |[-*] )/.test(lines[i]!)) para.push(lines[i++]!);
      blocks.push(<p key={key}>{inline(para.join(" "))}</p>);
    }
  }
  return <div className="md">{blocks}</div>;
}
