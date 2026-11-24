"""Checks for credentials that could leak. Values are never copied into the report."""

from __future__ import annotations

import ast
import fnmatch
import re
import subprocess
from pathlib import PurePosixPath
from typing import ClassVar

from shipshape.astutil import split_words, string_constants
from shipshape.checks.base import Check, plural
from shipshape.models import Dimension, Finding, Location, Severity
from shipshape.project import Project

ENV_FILE = re.compile(r"^\.env(\..+)?$")
SAFE_ENV_SUFFIXES = (".example", ".sample", ".template", ".dist")
VENDOR_KEY = re.compile(
    r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|"
    r"AIza[0-9A-Za-z_-]{35}|xox[baprs]-[A-Za-z0-9-]{10,}|hf_[A-Za-z0-9]{30,})"
)
SECRET_WORDS = frozenset({"secret", "token", "password", "passwd", "apikey", "credential"})
KEY_QUALIFIERS = frozenset({"api", "access", "private", "secret", "auth"})
PLACEHOLDER_HINTS = ("your", "xxx", "example", "placeholder", "changeme", "dummy", "<", "{", "env")


def _git_check_ignore(project: Project, rel: str) -> bool | None:
    """Ask git whether ``rel`` is ignored. ``None`` if git is unavailable or not a repository."""
    path = project.root / rel
    try:
        result = subprocess.run(
            ["git", "-C", str(path.parent), "check-ignore", "-q", "--no-index", path.name],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return {0: True, 1: False}.get(result.returncode)


def _gitignore_covers(project: Project, rel: str) -> bool:
    """Fallback without git: apply the project's .gitignore files, outermost first."""
    target = PurePosixPath(rel)
    ignored = False
    gitignores = sorted(project.files_matching(".gitignore"), key=lambda p: p.count("/"))
    for gitignore in gitignores:
        base = PurePosixPath(gitignore).parent
        if base.as_posix() != "." and base not in target.parents:
            continue
        relative = target.relative_to(base).as_posix() if base.as_posix() != "." else rel
        text = (project.root / gitignore).read_text(encoding="utf-8", errors="replace")
        for raw in text.splitlines():
            pattern = raw.strip()
            if not pattern or pattern.startswith("#"):
                continue
            negate = pattern.startswith("!")
            pattern = pattern.lstrip("!")
            anchored = "/" in pattern.strip("/")
            pattern = pattern.strip("/")
            subject = relative if anchored else target.name
            if fnmatch.fnmatch(subject, pattern):
                ignored = not negate
    return ignored


class EnvFileNotIgnored(Check):
    """A ``.env`` file that git would happily commit."""

    id: ClassVar[str] = "security.env-file-not-ignored"
    title: ClassVar[str] = ".env file is not git-ignored"
    severity: ClassVar[Severity] = Severity.CRITICAL
    dimension: ClassVar[Dimension] = Dimension.SECURITY
    concept: ClassVar[str] = "Keeping secrets out of git"

    def run(self, project: Project) -> list[Finding]:
        """Check every ``.env``-style file against git's ignore rules. Contents are not read."""
        findings = []
        for rel in project.files:
            name = PurePosixPath(rel).name
            if not ENV_FILE.match(name) or name.endswith(SAFE_ENV_SUFFIXES):
                continue
            verdict = _git_check_ignore(project, rel)
            if verdict is None:
                verdict = _gitignore_covers(project, rel)
                context = "This folder is not a git repository yet, and no .gitignore covers it."
            else:
                context = "Git would include it in the next commit."
            if verdict:
                continue
            message = (
                f"`{rel}` usually holds API keys and passwords. {context} Once it is pushed, "
                f"anyone who can see the repository can use those keys. Add `.env` to "
                f".gitignore, commit a `.env.example` with empty values instead, and rotate any "
                f"key that was ever committed."
            )
            findings.append(self.finding(message, [Location(path=rel)]))
        return findings


def _redact(value: str) -> str:
    return f"{value[:4]}… ({len(value)} characters, redacted)"


def _looks_like_secret_name(name: str) -> bool:
    words = set(split_words(name))
    return bool(words & SECRET_WORDS) or ("key" in words and bool(words & KEY_QUALIFIERS))


def _looks_like_secret_value(value: str) -> bool:
    lowered = value.lower()
    return (
        len(value) >= 12
        and not any(ch.isspace() for ch in value)
        and not re.fullmatch(r"[A-Z0-9_]+", value)
        and "://" not in value
        and not value.startswith(("/", "./", "~"))
        and not any(hint in lowered for hint in PLACEHOLDER_HINTS)
        and any(ch.isdigit() for ch in value)
        and any(ch.isalpha() for ch in value)
    )


def _named_values(tree: ast.AST) -> list[tuple[str, ast.Constant]]:
    pairs: list[tuple[str, ast.Constant]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
                pairs.append((name, node.value))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Constant):
            target = node.target
            name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
            pairs.append((name, node.value))
        elif isinstance(node, ast.keyword) and node.arg and isinstance(node.value, ast.Constant):
            pairs.append((node.arg, node.value))
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and isinstance(value, ast.Constant)
                ):
                    pairs.append((key.value, value))
    return pairs


class HardcodedSecret(Check):
    """API keys, tokens and passwords written directly into source code."""

    id: ClassVar[str] = "security.hardcoded-secret"
    title: ClassVar[str] = "Credentials written into the code"
    severity: ClassVar[Severity] = Severity.CRITICAL
    dimension: ClassVar[Dimension] = Dimension.SECURITY
    concept: ClassVar[str] = "Keeping secrets out of git"

    def run(self, project: Project) -> list[Finding]:
        """Match known key formats and credential-named variables with key-like values."""
        hits: dict[tuple[str, int], str] = {}
        for source in project.parsed:
            assert source.tree is not None
            for name, node in _named_values(source.tree):
                if (
                    isinstance(node.value, str)
                    and _looks_like_secret_name(name)
                    and _looks_like_secret_value(node.value)
                ):
                    hits[(source.path, node.lineno)] = node.value
            for node in string_constants(source.tree):
                match = VENDOR_KEY.search(str(node.value))
                if match:
                    hits[(source.path, node.lineno)] = match.group(0)
        if not hits:
            return []
        by_path = {s.path: s for s in project.sources}
        locations = [by_path[path].location(line) for path, line in sorted(hits)]
        message = (
            f"{plural(len(hits), 'credential-like value is', 'credential-like values are')} "
            f"written directly into the code. Anyone who can read the code, including everyone "
            f"on GitHub if it is pushed, can use them. Read them from environment variables "
            f"(or a git-ignored .env file) and rotate any key that was ever committed."
        )
        first = hits[min(hits)]
        return [self.finding(message, locations, evidence=_redact(first))]
