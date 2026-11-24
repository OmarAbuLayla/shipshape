"""Command-line interface: ``shipshape analyze``, ``shipshape eval``, ``shipshape checks``."""

from __future__ import annotations

import io
import sys
from collections import Counter, defaultdict
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from shipshape import __version__
from shipshape.analyzer import analyze_project
from shipshape.checks import RULES, default_checks
from shipshape.evaluation import case_root, evaluate, load_corpus, load_manifest
from shipshape.export import export, format_for_path
from shipshape.fixes import apply_fixes, fixable, project_zip
from shipshape.lessons import all_lessons, find_lesson
from shipshape.llm.cache import ExplanationCache
from shipshape.llm.client import FatalLLMError, LLMError, OpenAICompatibleClient, ping
from shipshape.llm.explain import DEFAULT_MAX_FINDINGS, explain_report
from shipshape.llm.settings import SettingsError, load_settings
from shipshape.models import Report
from shipshape.project import Project
from shipshape.render import (
    render_evaluation,
    render_explain_eval,
    render_fix_run,
    render_map_summary,
    render_report,
)
from shipshape.viewer import render_map_html

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Find what an engineer would object to in a Python project.",
)


@app.callback()
def _safe_output() -> None:
    """Never crash on characters the terminal's encoding lacks (Windows cp1252 pipes)."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="replace")


class OutputFormat(StrEnum):
    """How ``analyze`` prints its report."""

    TEXT = "text"
    JSON = "json"


ExplainOption = Annotated[
    bool,
    typer.Option(
        "--explain",
        help="Ask the configured LLM to explain findings and propose verified fixes (sends code).",
    ),
]
MaxFindingsOption = Annotated[
    int, typer.Option("--max-findings", min=1, help="Explain at most this many findings.")
]
NoCacheOption = Annotated[
    bool, typer.Option("--no-cache", help="Ignore stored explanations and ask the LLM again.")
]


def _scan(path: Path, explain: bool, max_findings: int, no_cache: bool) -> Report:
    """Analyse ``path`` and, if asked, add LLM explanations. Exits on user-facing errors."""
    return _scan_project(path, explain, max_findings, no_cache)[1]


def _scan_project(
    path: Path, explain: bool, max_findings: int, no_cache: bool
) -> tuple[Project, Report]:
    """Like :func:`_scan`, also returning the loaded project."""
    try:
        project = Project.load(path)
    except NotADirectoryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    report = analyze_project(project)
    if not explain or not report.findings:
        return project, report
    try:
        settings = load_settings()
        client = OpenAICompatibleClient(settings)
    except SettingsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    count = min(len(report.findings), max_findings)
    typer.echo(
        f"Sending code excerpts for {count} findings to {settings.provider} "
        f"({settings.model} at {settings.base_url}). Credentials are redacted first.",
        err=True,
    )
    try:
        explain_report(
            report,
            project,
            client,
            provider=settings.provider,
            max_findings=max_findings,
            cache=ExplanationCache(enabled=not no_cache),
            progress=lambda line: typer.echo(f"  {line}", err=True),
        )
    except FatalLLMError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    return project, report


@app.command()
def analyze(
    path: Annotated[Path, typer.Argument(help="Project folder to scan.")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Also write the JSON report here.")
    ] = None,
    output_format: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="Terminal output format.")
    ] = OutputFormat.TEXT,
    explain: ExplainOption = False,
    max_findings: MaxFindingsOption = DEFAULT_MAX_FINDINGS,
    no_cache: NoCacheOption = False,
    export_to: Annotated[
        Path | None,
        typer.Option(
            "--export",
            "-e",
            help="Export the findings; format from the extension (.json, .md, .csv).",
        ),
    ] = None,
) -> None:
    """Scan a project. Nothing in the project is executed."""
    export_format = None
    if export_to is not None:
        try:  # check before scanning, so a typo never costs an AI run
            export_format = format_for_path(export_to.name)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=2) from exc
    report = _scan(path, explain, max_findings, no_cache)
    payload = report.model_dump_json(indent=2)
    if output is not None:
        output.write_text(payload + "\n", encoding="utf-8")
    if export_to is not None and export_format is not None:
        export_to.write_text(export(report, export_format), encoding="utf-8")
    if output_format is OutputFormat.JSON:
        typer.echo(payload)
    else:
        render_report(report, Console())
        if output is not None:
            typer.echo(f"\nJSON report written to {output}")
        if export_to is not None:
            typer.echo(f"\nFindings exported to {export_to}")


@app.command("fix")
def fix(
    path: Annotated[Path, typer.Argument(help="Project folder to fix.")],
    patch: Annotated[
        Path | None, typer.Option("--patch", help="Write the fixes as a patch for `git apply`.")
    ] = None,
    zip_to: Annotated[
        Path | None, typer.Option("--zip", help="Write a fixed copy of the project as a zip.")
    ] = None,
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help="Only fix findings of this check id (repeatable)."),
    ] = None,
    max_findings: MaxFindingsOption = DEFAULT_MAX_FINDINGS,
    no_cache: NoCacheOption = False,
) -> None:
    """Explain findings, apply every verified fix to a copy, and scan the result again.

    The project folder itself is never changed. Without --patch or --zip, this only shows
    what the fixes would change.
    """
    for target in (patch, zip_to):
        if target is not None and target.resolve().is_relative_to(path.resolve()):
            typer.echo(f"Error: write {target} outside the project folder.", err=True)
            raise typer.Exit(code=2)
    project, report = _scan_project(path, True, max_findings, no_cache)
    chosen = [
        i
        for i, finding in enumerate(report.findings)
        if fixable(finding) and (not only or finding.check_id in only)
    ]
    if not chosen:
        typer.echo("No verified fixes to apply.")
        return
    result = apply_fixes(project, report, chosen)
    render_fix_run(result.run, report, Console())
    if patch is not None and result.texts:
        patch.write_text(result.run.patch, encoding="utf-8", newline="\n")
        typer.echo(f"\nPatch written to {patch} (apply with: git apply {patch.name})")
    if zip_to is not None and result.texts:
        try:
            zip_to.write_bytes(project_zip(project.root, result.texts, f"{project.name}-fixed"))
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f"\nFixed copy written to {zip_to}")
    if patch is None and zip_to is None:
        typer.echo("\nNothing was written. Use --patch or --zip to save the fixes.")


@app.command("map")
def draw_map(
    path: Annotated[Path, typer.Argument(help="Project folder to scan.")],
    html: Annotated[
        Path | None, typer.Option("--html", help="Write an interactive map page here.")
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write the graph as JSON here.")
    ] = None,
    explain: ExplainOption = False,
    max_findings: MaxFindingsOption = DEFAULT_MAX_FINDINGS,
    no_cache: NoCacheOption = False,
) -> None:
    """Build the architecture map: files, imports, missing pieces and where findings are."""
    report = _scan(path, explain, max_findings, no_cache)
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


@app.command("explain-eval")
def explain_eval(
    corpus: Annotated[Path, typer.Argument(help="Folder of projects with expected.yaml files.")],
    use_cache: Annotated[
        bool, typer.Option("--use-cache", help="Reuse stored explanations (cheaper, less honest).")
    ] = False,
) -> None:
    """Explain every finding in the corpus with the real LLM and report fix rates and cost.

    This calls the API for every finding (typically 30-50 calls) and costs money.
    """
    settings = load_settings()
    try:
        client = OpenAICompatibleClient(settings)
    except SettingsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    cache = ExplanationCache(enabled=use_cache)
    per_check: dict[str, Counter[str]] = defaultdict(Counter)
    totals: Counter[str] = Counter()
    cost = 0.0
    for case in load_corpus(corpus):
        with case_root(case) as root:
            project = Project.load(root)
            report = analyze_project(project)
            typer.echo(f"{case.name}: {len(report.findings)} findings", err=True)
            try:
                stats = explain_report(
                    report,
                    project,
                    client,
                    provider=settings.provider,
                    max_findings=len(report.findings) or 1,
                    cache=cache,
                )
            except FatalLLMError as exc:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(code=1) from exc
        for finding in report.findings:
            row = per_check[finding.check_id]
            row["findings"] += 1
            if finding.explanation is not None:
                row["explained"] += 1
                row[finding.explanation.fix_status.value] += 1
        for name in (
            "api_calls",
            "retries",
            "failures",
            "cache_hits",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
        ):
            totals[name] += getattr(stats, name)
        cost += stats.estimated_cost_usd or 0.0
    render_explain_eval(per_check, totals, cost, settings.model, Console())


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


@app.command("llm-check")
def llm_check(
    send: Annotated[
        bool,
        typer.Option("--ping", help="Send one tiny test request (costs a fraction of a cent)."),
    ] = False,
) -> None:
    """Show which LLM provider and model are configured, and whether a key is set."""
    try:
        settings = load_settings()
    except SettingsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if settings.env_file:
        typer.echo(f"Settings: {settings.env_file}")
    else:
        typer.echo(
            f"Settings: no .env found in {Path.cwd()} or its parent folders "
            f"(run from the shipshape folder, or set the variables in your environment)"
        )
    typer.echo(f"Provider: {settings.provider}")
    typer.echo(f"Model:    {settings.model}")
    typer.echo(f"Endpoint: {settings.base_url}")
    typer.echo(f"API key:  {settings.key_status()}")
    if not settings.api_key:
        raise typer.Exit(code=1)
    if not send:
        typer.echo("\nAdd --ping to send a test request.")
        return
    try:
        result = ping(settings)
    except (LLMError, SettingsError) as exc:
        typer.echo(f"\nTest request failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"\nTest request OK in {result.seconds:.1f}s: replied {result.reply!r} "
        f"({result.input_tokens} tokens in, {result.output_tokens} out)."
    )


@app.command("lessons")
def show_lessons(
    name: Annotated[
        str | None, typer.Argument(help="A lesson's slug, concept or check id; omit to list all.")
    ] = None,
) -> None:
    """Short lessons on the ideas behind every check."""
    console = Console()
    if name is None:
        table = Table(title="Lessons", show_lines=False)
        table.add_column("Lesson")
        table.add_column("Concept")
        table.add_column("Taught by")
        for lesson in all_lessons():
            table.add_row(lesson.slug, lesson.concept, ", ".join(lesson.checks))
        console.print(table)
        console.print("Show one with: shipshape lessons <lesson>")
        return
    found = find_lesson(name)
    if found is None:
        typer.echo(f"No lesson called {name!r}. Run `shipshape lessons` to list them.", err=True)
        raise typer.Exit(code=2)
    console.print(Markdown(f"# {found.concept}\n\n*{found.summary}*\n\n{found.body}"))


@app.command()
def version() -> None:
    """Print the engine version."""
    typer.echo(__version__)
