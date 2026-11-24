import { useState } from "react";

import { Check, Copy } from "../components/icons";
import { highlightPython } from "../lib/highlight";
import type { Edit } from "../lib/types";

function Line({ text, kind }: { text: string; kind: "del" | "add" }) {
  return (
    <span className={`ln ${kind}`}>
      {highlightPython(text).map((token, i) =>
        token.kind === "plain" ? token.text : <span key={i} className={`tok-${token.kind}`}>{token.text}</span>,
      )}
      {"\n"}
    </span>
  );
}

export function Diff({ edit }: { edit: Edit }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(edit.replace);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard blocked; the code is still selectable
    }
  };
  return (
    <div className="diff">
      <div className="file">
        <span>{edit.path}</span>
        <button className="btn ghost small" onClick={copy} aria-label="Copy the new code">
          {copied ? <Check size={14} /> : <Copy />} {copied ? "Copied" : "Copy new code"}
        </button>
      </div>
      <pre>
        {edit.search.split("\n").map((line, i) => <Line key={`d${i}`} text={line} kind="del" />)}
        {edit.replace.split("\n").map((line, i) => <Line key={`a${i}`} text={line} kind="add" />)}
      </pre>
    </div>
  );
}
