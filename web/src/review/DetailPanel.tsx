import { Alert, Book, Check } from "../components/icons";
import { capitalize, exclusionLines, formatLocation, plural, shortPath, splitSteps } from "../lib/format";
import type { ViewNode } from "../lib/graphModel";
import type { Block, Finding, Location, Report } from "../lib/types";
import { Diff } from "./Diff";

interface Props {
  report: Report;
  selected: number | null;
  box: ViewNode | null;
  onSelect: (index: number) => void;
  onOpenLocation: (location: Location) => void;
  onOpenFile: (path: string) => void;
  onSelectBlock: (id: string) => void;
  block: Block | null;
  chosen: Set<number>;
  onToggleFix: (index: number) => void;
}

/** True if the finding has a fix that passed every check. */
export function hasVerifiedFix(finding: Finding): boolean {
  return finding.explanation?.fix_status === "verified" && finding.explanation.edits.length > 0;
}

export function DetailPanel({ report, selected, box, block, onSelect, onOpenLocation, onOpenFile, onSelectBlock, chosen, onToggleFix }: Props) {
  const finding = selected === null ? null : report.findings[selected];
  return (
    <aside className="col detail" aria-label="Details">
      {finding ? (
        <FindingDetail
          finding={finding}
          number={(selected ?? 0) + 1}
          onLocate={onOpenLocation}
          included={chosen.has(selected ?? -1)}
          onToggleFix={() => selected !== null && onToggleFix(selected)}
        />
      ) : block ? (
        <BlockDetail block={block} report={report} onSelect={onSelect} onSelectBlock={onSelectBlock} />
      ) : box ? (
        <BoxDetail box={box} report={report} onSelect={onSelect} onOpenFile={onOpenFile} />
      ) : (
        <ProjectDetail report={report} onSelect={onSelect} />
      )}
    </aside>
  );
}

function Paragraphs({ text }: { text: string }) {
  // Turn `code` spans into <code> without dangerouslySetInnerHTML.
  const parts = text.split(/(`[^`]+`)/g);
  return (
    <p>
      {parts.map((part, i) =>
        part.startsWith("`") && part.endsWith("`") ? <code key={i}>{part.slice(1, -1)}</code> : part,
      )}
    </p>
  );
}

interface FindingDetailProps {
  finding: Finding;
  number: number;
  onLocate: (location: Location) => void;
  included: boolean;
  onToggleFix: () => void;
}

function FindingDetail({ finding, number, onLocate, included, onToggleFix }: FindingDetailProps) {
  const x = finding.explanation;
  return (
    <>
      <div className="detail-head">
        <div className="row">
          <span className={`pin ${finding.severity}`}>{number}</span>
          <h2>{finding.title}</h2>
        </div>
        <div className="tags">
          <span className={`chip ${finding.severity}`}>{finding.severity}</span>
          <span className="chip neutral">{finding.dimension}</span>
          {x?.fix_status === "verified" && <span className="chip verified">fix verified</span>}
          {x?.fix_status === "rejected" && <span className="chip rejected">fix rejected</span>}
        </div>
      </div>

      {x ? (
        <>
          <p className="summary">{x.summary}</p>
          <div className="sec">
            <h4>What's going on</h4>
            <Paragraphs text={x.what} />
          </div>
          <div className="sec">
            <h4>Why it matters</h4>
            <Paragraphs text={x.why} />
          </div>
          <div className="sec">
            <h4>How to fix it</h4>
            <ol>
              {splitSteps(x.how_to_fix).map((step, i) => (
                <li key={i}><Paragraphs text={step} /></li>
              ))}
            </ol>
          </div>
          {x.fix_status === "verified" && x.edits.length > 0 && (
            <div className="sec">
              <h4>Proposed fix</h4>
              <div style={{ display: "grid", gap: 8 }}>
                {x.edits.map((edit, i) => <Diff key={i} edit={edit} />)}
              </div>
              {x.behaviour_change && (
                <div className="headsup" style={{ marginTop: 6 }}>
                  <Alert />
                  <span><b>Heads-up.</b> {x.behaviour_change}</span>
                </div>
              )}
              <label className="include-fix">
                <input type="checkbox" checked={included} onChange={onToggleFix} />
                <span>Include this fix when applying fixes</span>
              </label>
              <div className="verified-note" style={{ marginTop: 6 }}>
                <Check />
                <span>
                  Checked before showing: it applies cleanly, the code still parses, the problem is gone and nothing new
                  was introduced. Shipshape does not run your code, so test it once after applying.
                </span>
              </div>
            </div>
          )}
          {x.fix_status === "rejected" && <p className="rejected-note">{x.fix_note}</p>}
        </>
      ) : (
        <>
          <div className="sec">
            <h4>What the check found</h4>
            <Paragraphs text={finding.message} />
          </div>
          <div className="cta">
            <p style={{ fontWeight: 600 }}>Want this in plain language, with a checked fix?</p>
            <p className="muted">Start a new scan with “Explain findings with AI” turned on.</p>
          </div>
        </>
      )}

      <div className="sec">
        <h4>Where</h4>
        <div className="locations">
          {finding.locations.slice(0, 12).map((location, i) => (
            <button key={i} onClick={() => onLocate(location)} title={`${formatLocation(location)} · show the code`}>
              {formatLocation({ ...location, path: shortPath(location.path) })}
            </button>
          ))}
          {finding.locations.length > 12 && (
            <span className="faint" style={{ fontSize: 12.5 }}>and {finding.locations.length - 12} more</span>
          )}
        </div>
      </div>

      <div className="concept">
        <span className="icon"><Book /></span>
        <span>
          <b>{finding.concept}</b>
          <span>The idea behind this finding. Short lessons arrive in a later version.</span>
        </span>
      </div>
    </>
  );
}

interface BoxDetailProps {
  box: ViewNode;
  report: Report;
  onSelect: (i: number) => void;
  onOpenFile: (path: string) => void;
}

function BoxDetail({ box, report, onSelect, onOpenFile }: BoxDetailProps) {
  const node = report.graph?.nodes.find((n) => n.id === box.members[0]);
  const isFile = box.members.length === 1 && node && box.kind !== "folder" && box.kind !== "group";
  return (
    <>
      <div className="detail-head">
        <p className="eyebrow">{box.kind === "folder" || box.kind === "group" ? "Folder" : capitalize(box.kind)}</p>
        <h2 className="mono" style={{ fontSize: 17, wordBreak: "break-all" }}>{isFile ? node.id : box.label}</h2>
      </div>
      {isFile && node ? (
        <div className="stat-grid">
          <div className="stat"><b>{node.lines_of_code}</b><span>lines of code</span></div>
          <div className="stat"><b>{node.functions}</b><span>functions</span></div>
          <div className="stat"><b>{node.max_complexity}</b><span>max complexity</span></div>
        </div>
      ) : (
        <p className="muted">{box.sub}</p>
      )}
      {isFile && node && node.third_party.length > 0 && (
        <p className="muted" style={{ fontSize: 13.5 }}>Uses {node.third_party.join(", ")}.</p>
      )}
      {isFile && node && report.files?.[node.id] && (
        <button className="btn small" style={{ justifySelf: "start" }} onClick={() => onOpenFile(node.id)}>
          Open the code ›
        </button>
      )}
      <FindingLinks indices={box.findings} report={report} onSelect={onSelect} empty="No findings in this part of the code." />
    </>
  );
}

function ProjectDetail({ report, onSelect }: { report: Report; onSelect: (i: number) => void }) {
  const stats = report.explain_stats;
  const counts = { critical: 0, major: 0, minor: 0 };
  for (const f of report.findings) counts[f.severity] += 1;
  return (
    <>
      <div className="detail-head">
        <p className="eyebrow">Overview</p>
        <h2>{plural(report.findings.length, "finding")}</h2>
      </div>
      <div className="stat-grid">
        <div className="stat"><b style={{ color: "var(--crit)" }}>{counts.critical}</b><span>fix first</span></div>
        <div className="stat"><b style={{ color: "var(--major)" }}>{counts.major}</b><span>worth fixing</span></div>
        <div className="stat"><b style={{ color: "var(--minor)" }}>{counts.minor}</b><span>polish</span></div>
      </div>
      {stats && (
        <p className="cost-line">
          {stats.findings_explained} explained by {stats.model} · {stats.fixes_verified} verified fixes ·{" "}
          {stats.api_calls} API calls{stats.api_calls > 0 && stats.estimated_cost_usd !== null ? ` · about $${stats.estimated_cost_usd.toFixed(3)}` : ""}
          {stats.cache_hits ? ` · ${stats.cache_hits} from cache` : ""}
        </p>
      )}
      {report.check_errors.map((error) => (
        <div className="notice" key={error}>{error}</div>
      ))}
      <ExcludedNote report={report} />
      <FindingLinks
        indices={report.findings.map((_, i) => i).slice(0, 8)}
        report={report}
        onSelect={onSelect}
        empty="No findings. This project is in good shape."
        title="Start here"
      />
    </>
  );
}

function FindingLinks({ indices, report, onSelect, empty, title = "Findings here" }: {
  indices: number[]; report: Report; onSelect: (i: number) => void; empty: string; title?: string;
}) {
  if (indices.length === 0) return <p className="muted">{empty}</p>;
  return (
    <div className="sec">
      <h4>{title}</h4>
      <div style={{ display: "grid", gap: 2 }}>
        {indices.map((i) => {
          const f = report.findings[i]!;
          return (
            <button key={i} className="issue" onClick={() => onSelect(i)}>
              <span className={`pin ${f.severity}`}>{i + 1}</span>
              <span>
                <div className="t">{f.title}</div>
                {f.explanation && <div className="w" style={{ whiteSpace: "normal", fontFamily: "var(--font-body)", fontSize: 12.5 }}>{f.explanation.summary}</div>}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** What the project asked to leave out, so the scores can always be traced back. */
function ExcludedNote({ report }: { report: Report }) {
  const lines = exclusionLines(report.exclusions);
  if (!lines.length) return null;
  return (
    <div className="excluded-note">
      <p className="eyebrow">Not included in the scores</p>
      <ul>
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <p className="hint">Set by the project itself, in .shipshapeignore files and inline comments.</p>
    </div>
  );
}

const BLOCK_KIND = { function: "Function", method: "Method", class: "Class", cell: "Notebook cell", module: "Module code" } as const;

/** One function, class, method or cell: size, calls both ways, and its findings. */
function BlockDetail({ block, report, onSelect, onSelectBlock }: {
  block: Block;
  report: Report;
  onSelect: (i: number) => void;
  onSelectBlock: (id: string) => void;
}) {
  const siblings = report.files?.[block.path]?.blocks ?? [];
  const calledBy = siblings.filter((b) => b.calls.includes(block.id));
  const calls = siblings.filter((b) => block.calls.includes(b.id));
  const links = (items: Block[], empty: string) =>
    items.length === 0 ? (
      <span className="faint">{empty}</span>
    ) : (
      items.map((b) => (
        <button key={b.id} className="block-link mono" onClick={() => onSelectBlock(b.id)}>{b.name}</button>
      ))
    );
  return (
    <>
      <div className="detail-head">
        <p className="eyebrow">{BLOCK_KIND[block.kind]}</p>
        <h2 className="mono" style={{ fontSize: 17, wordBreak: "break-all" }}>{block.name}</h2>
        <p className="faint mono" style={{ fontSize: 12.5 }}>{shortPath(block.path)} · lines {block.start_line}–{block.end_line}</p>
      </div>
      <div className="stat-grid">
        <div className="stat"><b>{block.lines_of_code}</b><span>lines of code</span></div>
        <div className="stat"><b>{block.complexity || "–"}</b><span>complexity</span></div>
        <div className="stat"><b>{block.kind === "cell" || block.kind === "module" ? "–" : block.has_docstring ? "yes" : "no"}</b><span>docstring</span></div>
      </div>
      <div className="sec">
        <h4>Calls</h4>
        <div className="block-links">{links(calls, "Nothing else in this file.")}</div>
      </div>
      <div className="sec">
        <h4>Called by</h4>
        <div className="block-links">{links(calledBy, "Nothing in this file.")}</div>
      </div>
      <p className="faint" style={{ fontSize: 12 }}>Calls are matched by name inside this file; calls from other files are not shown.</p>
      <FindingLinks indices={block.findings} report={report} onSelect={onSelect} empty="No findings in this block." />
    </>
  );
}
