"""Checks for whether someone else (or future you) can rerun the project and get the same result."""

from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from pathlib import PurePosixPath
from typing import ClassVar

from shipshape.astutil import (
    call_name,
    calls,
    get_keyword,
    is_constant,
    string_constants,
    top_level_imports,
)
from shipshape.checks.base import Check, examples, plural
from shipshape.imports import _raw_imports
from shipshape.models import Dimension, Finding, Location, Severity
from shipshape.project import Project

ABSOLUTE_PATH = re.compile(
    r"^(?:[A-Za-z]:[\\/]|\\\\[\w.$-]+[\\/]|/(?:home|Users|mnt|media|data|root|opt|srv|Volumes)/|~[\\/])"
)
ENVIRONMENT_FILES = (
    "requirements*.txt",
    "requirements*.in",
    "environment*.yml",
    "environment*.yaml",
    "conda*.yml",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "uv.lock",
)
PIN_MARKERS = re.compile(r"==|~=|===|\s@\s")
SEED_KEYWORDS = frozenset({"random_state", "seed", "generator", "rng"})
GLOBAL_SEED_CALLS = frozenset(
    {"manual_seed", "manual_seed_all", "set_seed", "set_random_seed", "seed_everything"}
)
STDLIB_RANDOM = frozenset(
    {"shuffle", "sample", "choice", "choices", "randint", "random", "uniform", "gauss", "randrange"}
)
TORCH_RANDOM = frozenset(
    {"rand", "randn", "randint", "randperm", "rand_like", "randn_like", "bernoulli", "multinomial"}
)
SHUFFLING_SPLITTERS = frozenset(
    {"KFold", "StratifiedKFold", "ShuffleSplit", "StratifiedShuffleSplit"}
)
WEIGHTED_LAYER_PREFIXES = (
    "Linear",
    "LazyLinear",
    "Bilinear",
    "Conv",
    "LazyConv",
    "LSTM",
    "GRU",
    "RNN",
    "Embedding",
    "MultiheadAttention",
    "Transformer",
)


def _is_machine_path(value: str) -> bool:
    """An absolute path with at least one concrete name after its root.

    A bare root such as ``/mnt/`` or ``D:\\`` is left out: it is usually the fixed part of a
    path built from variables (``f"/mnt/{drive}/{rest}"``), not a hard-coded location.
    """
    match = ABSOLUTE_PATH.match(value)
    if match is None or len(value) > 260 or "\n" in value:
        return False
    return bool(re.search(r"\w", value[match.end() :]))


def absolute_paths(tree: ast.AST) -> list[tuple[str, int]]:
    """(value, line) of every string literal that looks like a machine-specific absolute path."""
    return [
        (str(node.value), node.lineno)
        for node in string_constants(tree)
        if _is_machine_path(str(node.value))
    ]


class HardcodedPath(Check):
    """Absolute paths that only exist on the author's machine."""

    id: ClassVar[str] = "repro.hardcoded-path"
    title: ClassVar[str] = "Hard-coded absolute paths"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.REPRODUCIBILITY
    concept: ClassVar[str] = "Config over hard-coding"

    def run(self, project: Project) -> list[Finding]:
        """Find string literals that look like absolute, machine-specific paths.

        Test files are skipped: tests use absolute paths on purpose (to check path handling,
        or as fixed inputs) and never need to run on another machine's data folders.
        """
        hits: list[tuple[str, Location]] = []
        for source in project.parsed:
            if source.is_test:
                continue
            assert source.tree is not None
            hits.extend(
                (value, source.location(line)) for value, line in absolute_paths(source.tree)
            )
        if not hits:
            return []
        message = (
            f"{plural(len(hits), 'absolute path is', 'absolute paths are')} written into the "
            f"code, for example {examples([hits[0][0]], 1)}. Anyone else, or you on another "
            f"machine or a server, has to edit source code before it runs. Put paths in a "
            f"config file or a command-line argument, relative to the project."
        )
        return [self.finding(message, [loc for _, loc in hits], evidence=hits[0][0])]


def third_party_imports(project: Project) -> set[str]:
    """Top-level imported packages that are neither standard library nor part of the project."""
    local = project.local_module_names()
    found: set[str] = set()
    for source in project.parsed:
        assert source.tree is not None
        found |= top_level_imports(source.tree)
    return {
        name
        for name in found
        if name not in sys.stdlib_module_names and name not in local and name != "__future__"
    }


class MissingEnvironment(Check):
    """No file that says which packages the project needs."""

    id: ClassVar[str] = "repro.missing-environment"
    title: ClassVar[str] = "No list of dependencies"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.REPRODUCIBILITY
    concept: ClassVar[str] = "Reproducible environments"

    def run(self, project: Project) -> list[Finding]:
        """Flag projects with third-party imports but no requirements/environment file."""
        if project.files_matching(*ENVIRONMENT_FILES, max_depth=3):
            return []
        packages = sorted(third_party_imports(project))
        if not packages:
            return []
        message = (
            f"The code imports {plural(len(packages), 'third-party package')} "
            f"({examples(packages, 5)}) but there is no requirements.txt, environment.yml or "
            f"pyproject.toml. Nobody can recreate the environment, and in a few months even "
            f"you won't remember which versions worked."
        )
        return [self.finding(message, [Location(path=".")], evidence=", ".join(packages[:5]))]


class UnpinnedDependencies(Check):
    """Requirements without versions, so every fresh install can differ."""

    id: ClassVar[str] = "repro.unpinned-dependencies"
    title: ClassVar[str] = "Dependencies without pinned versions"
    severity: ClassVar[Severity] = Severity.MINOR
    dimension: ClassVar[Dimension] = Dimension.REPRODUCIBILITY
    concept: ClassVar[str] = "Reproducible environments"

    def run(self, project: Project) -> list[Finding]:
        """Inspect every requirements file line by line."""
        findings = []
        for rel in project.files_matching("requirements*.txt", "requirements*.in"):
            try:
                text = (project.root / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:  # unreadable requirements file: nothing to check in it
                continue
            total = 0
            unpinned: list[tuple[int, str]] = []
            for number, raw in enumerate(text.splitlines(), start=1):
                line = raw.split("#", 1)[0].strip()
                if not line or line.startswith(("-", "git+", "http", "./", "file:")):
                    continue
                total += 1
                if not PIN_MARKERS.search(f" {line} "):
                    unpinned.append((number, re.split(r"[\s<>=!~;\[]", line, maxsplit=1)[0]))
            if not unpinned:
                continue
            message = (
                f"{len(unpinned)} of {total} packages in `{rel}` have no exact version "
                f"({examples([name for _, name in unpinned])}). A fresh install next year can "
                f"pull versions that behave differently or break. Pin exact versions (for "
                f"example with `pip freeze`) for anything you report results from."
            )
            findings.append(
                self.finding(
                    message, [Location(path=rel, start_line=number) for number, _ in unpinned]
                )
            )
        return findings


def _has_seed_argument(call: ast.Call) -> bool:
    return any(kw.arg in SEED_KEYWORDS and not is_constant(kw.value, None) for kw in call.keywords)


def is_global_seed(call: ast.Call) -> bool:
    """True for calls such as ``torch.manual_seed(0)`` or ``np.random.seed(0)``."""
    parts = call_name(call).split(".")
    return parts[-1] in GLOBAL_SEED_CALLS or (parts[-1] == "seed" and "random" in parts)


def random_call(call: ast.Call) -> str | None:
    """Describe an unseeded source of randomness, or ``None`` if the call is deterministic."""
    name = call_name(call)
    parts = name.split(".")
    last = parts[-1]
    if _has_seed_argument(call):
        return None
    if parts[0] == "random" and len(parts) == 2 and last in STDLIB_RANDOM:
        return name
    if parts[0] in {"np", "numpy"} and "random" in parts[:-1]:
        if last == "default_rng":
            return None if call.args else name
        return None if last in {"seed", "RandomState", "Generator"} else name
    if parts[0] == "torch" and last in TORCH_RANDOM:
        return name
    if last in {"train_test_split", "random_split"}:
        return name
    # Every *ShuffleSplit (GroupShuffleSplit too) shuffles; KFold only with shuffle=True.
    if last.endswith("ShuffleSplit") or (
        last in SHUFFLING_SPLITTERS and is_constant(_value(get_keyword(call, "shuffle")), True)
    ):
        return name
    if last == "DataLoader" and is_constant(_value(get_keyword(call, "shuffle")), True):
        return f"{name}(shuffle=True)"
    return None


def _value(keyword: ast.keyword | None) -> ast.expr | None:
    return keyword.value if keyword is not None else None


def _first_torch_layer(tree: ast.AST) -> ast.Call | None:
    """First ``nn.<Layer>(...)`` with randomly initialised weights (not losses or activations)."""
    for call in calls(tree):
        parts = call_name(call).split(".")
        if "nn" in parts[:-1] and parts[-1].startswith(WEIGHTED_LAYER_PREFIXES):
            return call
    return None


class MissingSeed(Check):
    """Randomness everywhere, no seed anywhere."""

    id: ClassVar[str] = "repro.missing-seed"
    title: ClassVar[str] = "Random results with no seed"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.REPRODUCIBILITY
    concept: ClassVar[str] = "Reproducible experiments"

    def run(self, project: Project) -> list[Finding]:
        """Report unseeded randomness, unless a global seed is set anywhere in the project."""
        sites: list[tuple[str, Location]] = []
        for source in project.parsed:
            assert source.tree is not None
            for call in calls(source.tree):
                if is_global_seed(call):
                    return []
                description = random_call(call)
                if description:
                    sites.append((description, source.location(call.lineno)))
            if "torch" in top_level_imports(source.tree):
                layer = _first_torch_layer(source.tree)
                if layer is not None:
                    sites.append(("random weight init", source.location(layer.lineno)))
        if not sites:
            return []
        sites.sort(key=lambda site: (site[1].path, site[1].cell or 0, site[1].start_line or 0))
        message = (
            f"Randomness is used in {plural(len(sites), 'place')} "
            f"({examples([name for name, _ in sites])}) but no random seed is set anywhere. "
            f"Results change from run to run, so you can't tell whether a change actually "
            f"helped. Set one seed at the start (random, numpy and torch) and report results "
            f"over several seeds."
        )
        return [self.finding(message, [loc for _, loc in sites])]


def _folder(path: PurePosixPath) -> str:
    """A project folder as a POSIX string, ``""`` for the project root."""
    return "" if str(path) == "." else path.as_posix()


def _local_modules(project: Project) -> dict[str, list[str]]:
    """Top-level module name -> folders (``""`` for the root) that hold it as a file or package."""
    found: dict[str, list[str]] = defaultdict(list)
    for rel in project.files:
        path = PurePosixPath(rel)
        if path.suffix == ".py" and path.name != "__init__.py":
            found[path.stem].append(_folder(path.parent))
        elif path.name == "__init__.py" and len(path.parts) >= 2:
            found[path.parent.name].append(_folder(path.parent.parent))
    return found


def _reachable(folder: str, importer_dir: str) -> bool:
    """Python finds a module next to the running script, and (with ``-m``) from folders above."""
    return folder == "" or importer_dir == folder or importer_dir.startswith(folder + "/")


class BrokenLocalImport(Check):
    """Imports of project files that cannot work as the code is shipped."""

    id: ClassVar[str] = "repro.broken-local-import"
    title: ClassVar[str] = "Imports that only work on the author's setup"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.REPRODUCIBILITY
    concept: ClassVar[str] = "Explicit imports"

    def run(self, project: Project) -> list[Finding]:
        """Flag ``import x.py`` and imports of modules that exist only in other folders.

        Files inside packages, tests and files that change ``sys.path`` themselves are left
        out: there the search path is set up on purpose.
        """
        modules = _local_modules(project)
        locations: list[Location] = []
        examples_found: list[str] = []
        for source in project.parsed:
            assert source.tree is not None
            importer_dir = _folder(PurePosixPath(source.path).parent)
            in_package = f"{importer_dir}/__init__.py" in project.files if importer_dir else False
            if source.is_test or in_package or "sys.path" in source.text:
                continue
            for raw in _raw_imports(source.tree):
                if raw.level or not raw.module:
                    continue
                parts = raw.module.split(".")
                top = parts[0]
                if top in sys.stdlib_module_names or top not in modules:
                    continue
                if parts[-1] == "py" and len(parts) == 2:
                    problem = f"`{raw.module}`: drop the `.py`, it is `import {top}`"
                elif not any(_reachable(folder, importer_dir) for folder in modules[top]):
                    where = ", ".join(f"`{f or '.'}`" for f in sorted(modules[top])[:3])
                    problem = f"`{top}` only exists in {where}"
                else:
                    continue
                locations.append(source.location(raw.line))
                examples_found.append(f"{source.path}: {problem}")
        if not locations:
            return []
        message = (
            f"{plural(len(locations), 'import')} cannot work as the code is shipped: "
            f"{examples_found[0]}"
            + (f" (and {len(locations) - 1} more)" if len(locations) > 1 else "")
            + ". When the script runs, Python looks for modules next to it, not in other "
            "folders, so this only works with a hand-set PYTHONPATH or a file copied in by hand. "
            "Put shared code into one importable package, or import the file that is actually "
            "next to the script."
        )
        return [self.finding(message, locations, evidence="; ".join(examples_found[:4]))]
