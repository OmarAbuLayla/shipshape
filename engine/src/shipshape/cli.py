"""Command-line interface: ``shipshape analyze``, ``shipshape eval``, ``shipshape checks``."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from shipshape import __version__
from shipshape.analyzer import analyze as run_analysis
from shipshape.checks import RULES, default_checks
from shipshape.evaluation import evaluate, load_corpus, load_manifest
from shipshape.render import render_evaluation, render_map_summary, render_report
from shipshape.viewer import render_map_html

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Find what an engineer would object to in a Python project.",
)


class OutputFormat(StrEnum):
    """How ``analyze`` prints its report."""

    TEXT = "text"
    JSON = "json"


@app.command()
def analyze(
    path: Annotated[Path, typer.Argument(help="Project folder to scan.")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Also write the JSON report here.")
    ] = None,
    output_format: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="Terminal output format.")
    ] = OutputFormat.TEXT,
) -> None:
    """Scan a project. Nothing in the project is executed."""
    try:
        report = run_analysis(path)
    except NotADirectoryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    payload = report.model_dump_json(indent=2)
    if output is not None:
        output.write_text(payload + "\n", encoding="utf-8")
    if output_format is OutputFormat.JSON:
        typer.echo(payload)
    else:
        render_report(report, Console())
        if output is not None:
            typer.echo(f"\nJSON report written to {output}")


@app.command("map")
def draw_map(
    path: Annotated[Path, typer.Argument(help="Project folder to scan.")],
    html: Annotated[
        Path | None, typer.Option("--html", help="Write an interactive map page here.")
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write the graph as JSON here.")
    ] = None,
) -> None:
    """Build the architecture map: files, imports, missing pieces and where findings are."""
    try:
        report = run_analysis(path)
    except NotADirectoryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    render_map_summary(report, Console())
    if output is not None and report.graph is not None:
        output.write_text(report.graph.model_dump_json(indent=2) + "\n", encoding="utf-8")
        typer.echo(f"\nGraph JSON written to {output}")
    if html is not None:
        html.write_text(render_map_html(report), encoding="utf-8")
        typer.echo(
            f"\nMap written to {html}. Open it in a browser (needs internet for the layout)."
        )


@app.command("eval")
def evaluate_checks(
    corpus: Annotated[
        Path | None, typer.Argument(help="Folder of projects with expected.yaml files.")
    ] = None,
    manifest: Annotated[
        Path | None, typer.Option("--manifest", "-m", help="YAML list of external projects.")
    ] = None,
    strict: Annotated[
        bool, typer.Option("--strict", help="Exit with code 1 on any mistake.")
    ] = False,
) -> None:
    """Score every check's precision and recall against labelled projects."""
    if corpus is None and manifest is None:
        typer.echo("Error: give a corpus folder, --manifest, or both.", err=True)
        raise typer.Exit(code=2)
    cases = (load_corpus(corpus) if corpus else []) + (load_manifest(manifest) if manifest else [])
    result = evaluate(cases)
    render_evaluation(result, Console())
    if strict and not result.perfect:
        raise typer.Exit(code=1)


@app.command("checks")
def list_checks() -> None:
    """List every check with its dimension, default severity and concept."""
    table = Table()
    for column in ("Check", "Dimension", "Severity", "Concept"):
        table.add_column(column, overflow="fold")
    for check in default_checks():
        if check.id == "lint":
            continue
        table.add_row(check.id, check.dimension.value, check.severity.value, check.concept)
    for code, rule in RULES.items():
        table.add_row(
            f"{rule.check_id} ({code})", rule.dimension.value, rule.severity.value, rule.concept
        )
    Console().print(table)


@app.command()
def version() -> None:
    """Print the engine version."""
    typer.echo(__version__)
