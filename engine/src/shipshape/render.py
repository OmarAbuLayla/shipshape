"""Human-readable terminal output for reports and evaluations."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.text import Text

from shipshape.evaluation import EvalResult
from shipshape.models import Dimension, Location, Report, Severity

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

    for error in report.check_errors:
        console.print(f"[yellow]Check failed:[/] {error}")


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
