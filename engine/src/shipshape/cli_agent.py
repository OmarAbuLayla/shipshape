"""The ``shipshape agent`` command, kept apart from cli.py so each stays readable."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from shipshape.agent import AgentLimits, AgentStep, render_log, run_agent
from shipshape.checks.base import plural
from shipshape.fixes import project_zip
from shipshape.llm.client import FatalLLMError, LLMError, OpenAICompatibleClient
from shipshape.llm.settings import SettingsError, load_settings
from shipshape.project import Project


def refuse_targets_inside(path: Path, *targets: Path | None) -> None:
    """Exit if an output file would be written into the project being fixed."""
    for target in targets:
        if target is not None and target.resolve().is_relative_to(path.resolve()):
            typer.echo(f"Error: write {target} outside the project folder.", err=True)
            raise typer.Exit(code=2)


def agent_command(
    path: Annotated[Path, typer.Argument(help="Project folder to improve.")],
    patch: Annotated[
        Path | None, typer.Option("--patch", help="Write the agent's fixes as a patch.")
    ] = None,
    zip_to: Annotated[
        Path | None, typer.Option("--zip", help="Write a fixed copy of the project as a zip.")
    ] = None,
    log: Annotated[
        Path | None, typer.Option("--log", help="Write the step-by-step log as Markdown.")
    ] = None,
    max_steps: Annotated[
        int, typer.Option("--max-steps", min=1, max=200, help="Stop after this many model turns.")
    ] = AgentLimits.max_steps,
    max_cost: Annotated[
        float, typer.Option("--max-cost", min=0.0, help="Stop at this estimated cost in USD.")
    ] = AgentLimits.max_cost_usd,
) -> None:
    """Let an LLM agent fix findings with verified edits, on a copy, step by step.

    The agent reads code and proposes fixes; Shipshape verifies each one and applies only those
    that pass, in memory. The project folder is never changed.
    """
    refuse_targets_inside(path, patch, zip_to, log)
    try:
        project = Project.load(path)
        settings = load_settings()
        client = OpenAICompatibleClient(settings)
    except (NotADirectoryError, SettingsError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        f"Agent: {settings.model} at {settings.base_url} reads the project's Python files "
        f"(credentials redacted). Limits: {max_steps} turns, ${max_cost:.2f}.",
        err=True,
    )

    def show(step: AgentStep) -> None:
        mark = "ok" if step.ok else "!!"
        typer.echo(f"  {step.number:>3}. [{mark}] {step.tool} {step.detail}", err=True)

    try:
        result = run_agent(project, client, AgentLimits(max_steps, max_cost), show)
    except FatalLLMError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except LLMError as exc:
        typer.echo(f"Error: the model call failed ({exc}). Nothing was written.", err=True)
        raise typer.Exit(code=1) from exc
    run = result.run
    cost = f", about ${run.estimated_cost_usd:.4f}" if run.estimated_cost_usd is not None else ""
    typer.echo(
        f"\nStopped: {run.stopped_because}. Grade {run.before_grade} -> {run.after_grade}, "
        f"{plural(len(run.fixes_applied), 'verified fix', 'verified fixes')} applied to a copy "
        f"({run.turns} turns{cost})."
    )
    if run.summary:
        typer.echo(f"\n{run.summary}")
    if log is not None:
        log.write_text(render_log(run), encoding="utf-8")
        typer.echo(f"\nLog written to {log}")
    if patch is not None and result.texts:
        patch.write_bytes(run.patch.encode("utf-8"))
        typer.echo(f"Patch written to {patch} (apply with: git apply {patch.name})")
    if zip_to is not None and result.texts:
        try:
            zip_to.write_bytes(project_zip(project.root, result.texts, f"{project.name}-fixed"))
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f"Fixed copy written to {zip_to}")
    if result.texts and patch is None and zip_to is None:
        typer.echo("\nNo fixes were saved. Use --patch or --zip to keep them.")
