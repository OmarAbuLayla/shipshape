"""A curated subset of ruff's rules, translated into Shipshape findings.

Only rules that point to real bugs or clear readability problems are enabled. Ruff's full
rule set would bury the important findings, which defeats the teaching purpose.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from shipshape.checks.base import Check, plural
from shipshape.models import Dimension, Finding, Location, Severity
from shipshape.project import Project


@dataclass(frozen=True)
class Rule:
    """How one ruff rule is presented."""

    check_id: str
    title: str
    dimension: Dimension
    severity: Severity
    concept: str
    explanation: str


RULES: dict[str, Rule] = {
    "F821": Rule(
        "lint.undefined-name",
        "Names that don't exist",
        Dimension.CORRECTNESS,
        Severity.CRITICAL,
        "How Python resolves names",
        "These lines crash with NameError as soon as they run, usually after a rename.",
    ),
    "B006": Rule(
        "lint.mutable-default",
        "Mutable default arguments",
        Dimension.CORRECTNESS,
        Severity.MAJOR,
        "Mutable default arguments",
        "A list or dict default is created once and shared between calls, so data leaks "
        "from one call into the next. Default to None and create it inside the function.",
    ),
    "B023": Rule(
        "lint.loop-closure",
        "Functions capture a loop variable",
        Dimension.CORRECTNESS,
        Severity.MINOR,
        "Closures and late binding",
        "If these functions run later (callbacks, a list of functions), they all see the loop "
        "variable's last value, not the value from their own iteration. Bind it as a default "
        "argument (`lambda q=query: ...`). If they run immediately inside the loop, as with a "
        "retry helper, it is safe, but binding it still makes that obvious to readers.",
    ),
    "F811": Rule(
        "lint.redefined-name",
        "Definitions overwritten before use",
        Dimension.CORRECTNESS,
        Severity.MAJOR,
        "One name, one meaning",
        "A name is defined again before the first definition was used, so one of them is dead "
        "code and it is unclear which one runs.",
    ),
    "F401": Rule(
        "lint.unused-import",
        "Unused imports",
        Dimension.READABILITY,
        Severity.MINOR,
        "Keeping code lean",
        "Unused imports slow down loading and suggest dependencies the code doesn't have.",
    ),
    "F841": Rule(
        "lint.unused-variable",
        "Unused variables",
        Dimension.READABILITY,
        Severity.MINOR,
        "Keeping code lean",
        "A value is computed and never used: either dead code, or a bug where it should "
        "have been used.",
    ),
    "F403": Rule(
        "lint.star-import",
        "Star imports",
        Dimension.READABILITY,
        Severity.MINOR,
        "Explicit imports",
        "`from x import *` hides where names come from and can silently overwrite your own.",
    ),
    "E711": Rule(
        "lint.none-comparison",
        "Comparisons with == None",
        Dimension.READABILITY,
        Severity.MINOR,
        "Idiomatic Python",
        "Use `is None` / `is not None`; `==` can be overridden and behaves oddly with arrays.",
    ),
    "E712": Rule(
        "lint.bool-comparison",
        "Comparisons with == True / False",
        Dimension.READABILITY,
        Severity.MINOR,
        "Idiomatic Python",
        "Write `if flag:` or `if not flag:` instead of comparing to True or False.",
    ),
    "PLW0603": Rule(
        "lint.global-statement",
        "Functions change global variables",
        Dimension.STRUCTURE,
        Severity.MINOR,
        "Avoiding global state",
        "Global state makes behaviour depend on call order and makes functions hard to test. "
        "Pass values in and return results instead.",
    ),
    "PLR0913": Rule(
        "lint.too-many-arguments",
        "Functions with too many parameters",
        Dimension.STRUCTURE,
        Severity.MINOR,
        "Small interfaces",
        "More than five parameters is hard to call correctly. Group related ones into a "
        "dataclass or config object.",
    ),
}


class RuffCheck(Check):
    """Runs ruff once and turns each triggered rule into one finding."""

    id: ClassVar[str] = "lint"
    title: ClassVar[str] = "Lint"
    severity: ClassVar[Severity] = Severity.MINOR
    dimension: ClassVar[Dimension] = Dimension.READABILITY
    concept: ClassVar[str] = "Linting"

    def run(self, project: Project) -> list[Finding]:
        """Run ruff with the curated rules; notebooks are skipped (handled by other checks)."""
        command = [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--isolated",
            "--no-cache",
            "--exit-zero",
            "--output-format",
            "json",
            "--select",
            ",".join(RULES),
            "--extend-exclude",
            "*.ipynb,build,env",
            str(project.root),
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", timeout=300, check=False
        )
        if result.returncode != 0:
            raise RuntimeError(f"ruff failed: {result.stderr.strip()[:300]}")
        return self.translate(json.loads(result.stdout or "[]"), project.root)

    @staticmethod
    def translate(items: list[dict[str, object]], root: Path) -> list[Finding]:
        """Group ruff's JSON diagnostics by rule into findings."""
        grouped: dict[str, list[Location]] = defaultdict(list)
        for item in items:
            code = str(item.get("code"))
            location = item.get("location")
            if code not in RULES or not isinstance(location, dict):
                continue
            try:
                path = Path(str(item["filename"])).resolve().relative_to(root.resolve())
            except (KeyError, ValueError):
                continue
            row = location.get("row")
            grouped[code].append(
                Location(path=path.as_posix(), start_line=row if isinstance(row, int) else None)
            )
        findings = []
        for code, locations in grouped.items():
            rule = RULES[code]
            files = len({loc.path for loc in locations})
            message = (
                f"{plural(len(locations), 'place')} in {plural(files, 'file')}. {rule.explanation}"
            )
            findings.append(
                Finding(
                    check_id=rule.check_id,
                    title=rule.title,
                    severity=rule.severity,
                    dimension=rule.dimension,
                    concept=rule.concept,
                    message=message,
                    locations=locations,
                    evidence=f"ruff {code}",
                )
            )
        return findings
