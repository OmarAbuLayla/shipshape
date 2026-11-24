import { useEffect, useRef, useState } from "react";

const FORMATS = [
  { format: "md", label: "Markdown", hint: "Readable report for issues, READMEs or email" },
  { format: "json", label: "JSON", hint: "The complete report, for other tools" },
  { format: "csv", label: "CSV", hint: "One row per location, for spreadsheets" },
] as const;

/** Download the findings (with AI explanations when the scan has them). */
export function ExportMenu({ scanId }: { scanId: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !root.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <div className="export" ref={root}>
      <button className="btn small" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        Export ▾
      </button>
      {open && (
        <div className="export-menu" role="menu">
          {FORMATS.map((item) => (
            <a
              key={item.format}
              role="menuitem"
              href={`/api/scans/${scanId}/export?format=${item.format}`}
              download
              onClick={() => setOpen(false)}
            >
              <b>{item.label}</b>
              <span>{item.hint}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
