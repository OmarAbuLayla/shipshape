import { Close } from "../components/icons";
import { capitalize, formatLocation, plural } from "../lib/format";
import { DIMENSIONS, SEVERITIES, type Dimension, type Finding } from "../lib/types";

interface Props {
  findings: Finding[];
  visible: number[]; // indices to show, already filtered by box
  selected: number | null;
  onSelect: (index: number) => void;
  dimension: Dimension | null;
  onDimension: (dimension: Dimension | null) => void;
  boxLabel: string | null;
  onClearBox: () => void;
}

const GROUP_TITLE = { critical: "Fix first", major: "Worth fixing", minor: "Polish" } as const;

export function IssueList({ findings, visible, selected, onSelect, dimension, onDimension, boxLabel, onClearBox }: Props) {
  const present = DIMENSIONS.filter((d) => findings.some((f) => f.dimension === d));
  const shown = visible.filter((i) => !dimension || findings[i]?.dimension === dimension);
  let number = 0;
  const numberOf = new Map(findings.map((_, i) => [i, ++number]));

  return (
    <nav className="col issues" aria-label="Findings">
      <div className="issues-tools">
        <div className="filters" role="group" aria-label="Filter by quality dimension">
          <button aria-pressed={dimension === null} onClick={() => onDimension(null)}>
            All {findings.length}
          </button>
          {present.map((d) => (
            <button key={d} aria-pressed={dimension === d} onClick={() => onDimension(dimension === d ? null : d)}>
              {capitalize(d)}
            </button>
          ))}
        </div>
        {boxLabel && (
          <div className="node-filter">
            <span style={{ minWidth: 0, display: "flex", gap: 6, alignItems: "center" }}>
              On map: <code>{boxLabel}</code>
            </span>
            <button className="btn ghost small" onClick={onClearBox} aria-label="Show all findings" style={{ height: 22, padding: "0 4px" }}>
              <Close />
            </button>
          </div>
        )}
      </div>

      {shown.length === 0 && <p className="muted" style={{ padding: "16px 10px", fontSize: 14 }}>No findings here.</p>}

      {SEVERITIES.map((severity) => {
        const items = shown.filter((i) => findings[i]?.severity === severity);
        if (items.length === 0) return null;
        return (
          <div key={severity}>
            <div className="group-label">
              {GROUP_TITLE[severity]} · {plural(items.length, "issue")}
            </div>
            {items.map((index) => {
              const finding = findings[index]!;
              const first = finding.locations[0];
              const more = finding.locations.length - 1;
              const status = finding.explanation?.fix_status;
              return (
                <button
                  key={index}
                  className="issue"
                  aria-pressed={selected === index}
                  onClick={() => onSelect(index)}
                >
                  <span className={`pin ${finding.severity}`}>{numberOf.get(index)}</span>
                  <span style={{ minWidth: 0 }}>
                    <div className="t">{finding.title}</div>
                    <div className="w">
                      {first ? formatLocation(first) : ""}
                      {more > 0 ? ` +${more} more` : ""}
                    </div>
                    {(status === "verified" || finding.explanation) && (
                      <div className="tags">
                        {status === "verified" && <span className="chip verified">fix ready</span>}
                        {finding.explanation && status !== "verified" && <span className="chip neutral">explained</span>}
                      </div>
                    )}
                  </span>
                </button>
              );
            })}
          </div>
        );
      })}
    </nav>
  );
}
