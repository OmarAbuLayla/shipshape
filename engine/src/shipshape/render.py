"""Human-readable terminal output for reports and evaluations."""

from __future__ import annotations

from collections import Counter

from rich.console import Console
from rich.table import Table
from rich.text import Text

from shipshape.evaluation import EvalResult
from shipshape.export import describe_exclusions
from shipshape.models import Dimension, EdgeKind, Edit, Location, NodeKind, Report, Severity

SEVERITY_STYLE: dict[Severity, str] = {
    Severity.CRITICAL: "bold red",
    Severity.MAJOR: "dark_orange",
    Severity.MINOR: "grey58",
}
MAX_LOCATIONS_SHOWN = 3


def format_location(location: Location) -> str:
    """``path:line`` or ``path [cell 2]:line``; ``(project)`` for project-wide findings."""
    if location.path == ".":
        return "(project)"
    text = location.path
    if location.cell is not None:
        text += f" [cell {location.cell}]"
    if location.start_line is not None:
        text += f":{location.start_line}"
    return text


def _score_bar(score: int, width: int = 20) -> Text:
    filled = round(score / 100 * width)
    style = "green" if score >= 75 else "yellow" if score >= 50 else "red"
    return Text("#" * filled, style=style) + Text("-" * (width - filled), style="grey35")


def render_report(report: Report, console: Console) -> None:
    """Print the scorecard and a table of findings."""
    stats = report.stats
    console.print(
        f"[bold]{report.project_name}[/]  {stats.python_files} Python files, "
        f"{stats.notebooks} notebooks, {stats.lines_of_code:,} lines of code"
    )
    console.print()

    scorecard = Table(show_header=False, box=None, padding=(0, 1))
    for dimension in Dimension:
        score = report.scores.get(dimension, 100)
        scorecard.add_row(dimension.value.capitalize(), _score_bar(score), f"{score:>3}")
    console.print(scorecard)
    console.print(f"\nOverall grade: [bold]{report.grade}[/]  [grey58](rough guide)[/]\n")
    excluded = describe_exclusions(report.exclusions)
    if excluded:
        console.print("[bold]Not included in the scores[/] (on this project's own request):")
        for line in excluded:
            console.print(f"  - {line.replace('`', '')}", highlight=False, markup=False)
        console.print()

    if not report.findings:
        console.print("[green]No findings.[/]")
    else:
        table = Table(show_lines=True, expand=True)
        table.add_column("Severity", no_wrap=True)
        table.add_column("Finding", ratio=2)
        table.add_column("Where", ratio=1)
        for finding in report.findings:
            shown = [format_location(loc) for loc in finding.locations[:MAX_LOCATIONS_SHOWN]]
            hidden = len(finding.locations) - MAX_LOCATIONS_SHOWN
            if hidden > 0:
                shown.append(f"+{hidden} more")
            body = Text(finding.title, style="bold") + Text(f"\n{finding.message}")
            body += Text(f"\nConcept: {finding.concept}", style="cyan")
            table.add_row(
                Text(finding.severity.value, style=SEVERITY_STYLE[finding.severity]),
                body,
                "\n".join(shown),
            )
        console.print(table)

    render_explanations(report, console)
    for error in report.check_errors:
        console.print(f"[yellow]Check failed:[/] {error}")


FIX_STYLE = {"verified": "green", "rejected": "red", "none": "grey58"}


def _diff(edit: Edit) -> Text:
    text = Text(f"{edit.path}\n", style="bold")
    for line in edit.search.splitlines():
        text += Text(f"- {line}\n", style="red")
    for line in edit.replace.splitlines():
        text += Text(f"+ {line}\n", style="green")
    return text


def render_explanations(report: Report, console: Console) -> None:
    """Print each explanation with its fix (as a diff) and what the run cost."""
    explained = [f for f in report.findings if f.explanation is not None]
    if not explained:
        return
    console.rule("[bold]Explanations", characters="-")
    for finding in explained:
        explanation = finding.explanation
        assert explanation is not None
        status = explanation.fix_status.value
        console.print(
            f"\n[bold]{finding.title}[/]  [{FIX_STYLE[status]}]fix: {status}[/]"
            + ("  [grey58](cached)[/]" if explanation.cached else "")
        )
        console.print(f"[italic]{explanation.summary}[/]")
        console.print(f"[bold]What's going on.[/] {explanation.what}")
        console.print(f"[bold]Why it matters.[/] {explanation.why}")
        console.print(f"[bold]How to fix it.[/] {explanation.how_to_fix}")
        if explanation.fix_status.value == "verified":
            for edit in explanation.edits:
                console.print(_diff(edit))
            if explanation.behaviour_change:
                console.print(f"[bold yellow]Heads-up:[/] {explanation.behaviour_change}")
        if explanation.fix_note:
            console.print(f"[grey58]{explanation.fix_note}[/]")
        console.print(f"[cyan]Concept: {finding.concept}[/]")
    stats = report.explain_stats
    if stats is not None:
        cost = (
            f"about ${stats.estimated_cost_usd:.4f} at peak prices"
            if stats.estimated_cost_usd is not None
            else "cost unknown for this model"
        )
        console.rule(characters="-")
        console.print(
            f"{stats.findings_explained} explained with {stats.model}: {stats.api_calls} API calls "
            f"({stats.retries} retries, {stats.cache_hits} from cache, {stats.failures} failed), "
            f"{stats.input_tokens:,} tokens in ({stats.cached_input_tokens:,} cached), "
            f"{stats.output_tokens:,} out, {cost}, {stats.seconds:.0f}s. "
            f"Fixes: {stats.fixes_verified} verified, {stats.fixes_rejected} rejected."
        )


def render_explain_eval(
    per_check: dict[str, Counter[str]],
    totals: Counter[str],
    cost: float,
    model: str,
    console: Console,
) -> None:
    """Print how often explanations and fixes succeeded per check, and the total cost."""
    table = Table(title=f"Explanations with {model}")
    for column in ("Check", "Findings", "Explained", "Verified", "Rejected", "No fix"):
        table.add_column(column, justify="left" if column == "Check" else "right")
    for check_id, row in sorted(per_check.items()):
        table.add_row(
            check_id,
            *(str(row[key]) for key in ("findings", "explained", "verified", "rejected", "none")),
        )
    console.print(table)
    console.print(
        f"{totals['api_calls']} API calls, {totals['retries']} retries, "
        f"{totals['failures']} failures, {totals['cache_hits']} cache hits; "
        f"{totals['input_tokens']:,} tokens in ({totals['cached_input_tokens']:,} cached), "
        f"{totals['output_tokens']:,} out; about ${cost:.4f} at peak prices."
    )


def render_map_summary(report: Report, console: Console) -> None:
    """Print what the architecture map contains, for a quick look without a browser."""
    graph = report.graph
    if graph is None:
        console.print("[yellow]No map could be built.[/]")
        return
    kinds = Counter(node.kind.value for node in graph.nodes)
    edges = Counter(edge.kind.value for edge in graph.edges)
    console.print(f"[bold]{report.project_name}[/]  map")
    console.print(
        "  Nodes: " + ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items()))
    )
    console.print("  Edges: " + (", ".join(f"{c} {k}" for k, c in sorted(edges.items())) or "none"))

    imported_by = Counter(e.target for e in graph.edges if e.kind is EdgeKind.IMPORT)
    if imported_by:
        console.print("\n[bold]Most depended-on modules[/]")
        for path, count in imported_by.most_common(5):
            console.print(f"  {count:>3}  {path}")

    # Package __init__ files are loaded implicitly, so "nothing imports them" means nothing.
    tested = {e.target for e in graph.edges if e.kind is EdgeKind.TEST}
    tested |= {n.id for n in graph.nodes if n.label == "__init__.py"}
    library = [n for n in graph.nodes if n.kind is NodeKind.MODULE and n.role == "library"]
    unused = [n.id for n in library if n.id not in imported_by and n.id not in tested]
    if unused:
        console.print("\n[bold]Library modules nothing imports[/] [grey58](dead code?)[/]")
        for path in unused[:10]:
            console.print(f"       {path}")
        if len(unused) > 10:
            console.print(f"       +{len(unused) - 10} more")
    if graph.unresolved_imports:
        console.print(
            f"\n[grey58]{len(graph.unresolved_imports)} local-looking imports could not be "
            f"matched to a file (dynamic imports or sys.path tricks).[/]"
        )


def _ratio(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def render_evaluation(result: EvalResult, console: Console) -> None:
    """Print precision and recall per check, then every mistake."""
    table = Table(title="Checks vs. expected issues")
    for column in ("Check", "Precision", "Recall", "TP", "FP", "Found", "Missed"):
        table.add_column(column, justify="left" if column == "Check" else "right")
    for check_id, score in sorted(result.scores.items()):
        table.add_row(
            check_id,
            _ratio(score.precision),
            _ratio(score.recall),
            str(score.true_positives),
            str(score.false_positives),
            str(score.found),
            str(score.missed),
        )
    console.print(table)
    for mistake in result.mistakes:
        console.print(f"[red]x[/] {mistake}")
    for error in result.errors:
        console.print(f"[yellow]Check failed:[/] {error}")
    if result.perfect:
        console.print("[green]Every expected issue found, no false positives.[/]")
