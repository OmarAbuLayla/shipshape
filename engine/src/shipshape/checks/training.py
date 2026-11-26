"""Checks for deep-learning training and evaluation code (PyTorch-style loops).

These target bugs that make results wrong without any error: gradients that pile up across
batches, evaluation with dropout and batch norm still in training mode, and a test set that is
quietly used to choose the model.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from typing import ClassVar

from shipshape.astutil import calls, last_name, split_words
from shipshape.checks.base import Check, plural
from shipshape.models import Dimension, Finding, Location, Severity
from shipshape.project import Project, SourceFile

LOOPS = (ast.For, ast.AsyncFor, ast.While)
NO_GRAD_CONTEXTS = frozenset({"no_grad", "inference_mode"})
# Keyword arguments through which a held-out set steers training (early stopping, eval sets).
SELECTION_KEYWORDS = frozenset(
    {"validation_data", "eval_set", "valid_sets", "evals", "eval_dataset", "early_stopping_data"}
)


def _innermost_training_loops(tree: ast.AST) -> Iterator[ast.For | ast.AsyncFor | ast.While]:
    """Loops that call ``.backward()`` themselves, not only through a nested loop."""
    for node in ast.walk(tree):
        if not isinstance(node, LOOPS):
            continue
        nested = [n for n in ast.walk(node) if isinstance(n, LOOPS) and n is not node]
        inner = {id(c) for loop in nested for c in calls(loop)}
        if any(last_name(c) == "backward" and id(c) not in inner for c in calls(node)):
            yield node


def _calls_named(node: ast.AST, *names: str) -> list[ast.Call]:
    return [c for c in calls(node) if last_name(c) in names]


class MissingZeroGrad(Check):
    """A training loop that never clears gradients, so they accumulate across batches."""

    id: ClassVar[str] = "correctness.missing-zero-grad"
    title: ClassVar[str] = "Gradients are never reset in the training loop"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.CORRECTNESS
    concept: ClassVar[str] = "Training loops that behave"

    def run(self, project: Project) -> list[Finding]:
        """Flag loops with ``backward()`` and ``step()`` but no ``zero_grad()`` inside."""
        locations: list[Location] = []
        for source in project.parsed:
            assert source.tree is not None
            for loop in _innermost_training_loops(source.tree):
                if _calls_named(loop, "step") and not _calls_named(loop, "zero_grad"):
                    locations.append(source.location(loop.lineno))
        if not locations:
            return []
        message = (
            f"{plural(len(locations), 'training loop calls', 'training loops call')} "
            f"`backward()` and `step()` but never `zero_grad()` inside the loop. PyTorch adds "
            f"new gradients to the old ones, so every update also carries the gradients of all "
            f"earlier batches: training silently goes wrong. Call `optimizer.zero_grad()` at "
            f"the start of each iteration (or only every k steps, on purpose, for gradient "
            f"accumulation)."
        )
        return [self.finding(message, locations)]


def _switches_mode(tree: ast.AST) -> bool:
    """``model.eval()``, or ``model.train(flag)`` with anything but a literal ``True``."""
    for call in calls(tree):
        if last_name(call) == "eval" and not call.args:
            return True
        if last_name(call) == "train" and call.args:
            flag = call.args[0]
            if not (isinstance(flag, ast.Constant) and flag.value is True):
                return True
    return False


def _no_grad_blocks(tree: ast.AST) -> list[ast.With | ast.AsyncWith]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.With | ast.AsyncWith)
        and any(
            isinstance(item.context_expr, ast.Call)
            and last_name(item.context_expr) in NO_GRAD_CONTEXTS
            for item in node.items
        )
    ]


class MissingEvalMode(Check):
    """Training code that evaluates without ever switching the model to evaluation mode."""

    id: ClassVar[str] = "correctness.missing-eval-mode"
    title: ClassVar[str] = "Evaluation runs with the model still in training mode"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.CORRECTNESS
    concept: ClassVar[str] = "Training loops that behave"

    def run(self, project: Project) -> list[Finding]:
        """Flag files that train (``backward()``) and evaluate (``no_grad``) but never ``eval()``.

        Files that switch the mode anywhere (``.eval()``, or ``.train(flag)`` with a flag that
        can be False) are left alone, so evaluation helpers whose caller switches the mode are
        not reported.
        """
        locations: list[Location] = []
        for source in project.parsed:
            assert source.tree is not None
            if not _calls_named(source.tree, "backward") or _switches_mode(source.tree):
                continue
            locations += [source.location(b.lineno) for b in _no_grad_blocks(source.tree)]
        if not locations:
            return []
        message = (
            f"{plural(len(locations), 'evaluation block runs', 'evaluation blocks run')} under "
            f"`torch.no_grad()` in training code that never calls `model.eval()`. `no_grad` "
            f"only stops gradients: dropout keeps dropping units and batch norm keeps using "
            f"(and updating) batch statistics, so validation and test scores are noisy and "
            f"usually too low. Call `model.eval()` before evaluating and `model.train()` "
            f"before training again."
        )
        return [self.finding(message, locations)]


def _mentions_test(node: ast.AST) -> bool:
    """True if ``node`` uses a name like ``X_test``, ``test_loader`` or ``test_ds``."""
    for child in ast.walk(node):
        name = (
            child.id
            if isinstance(child, ast.Name)
            else child.attr
            if isinstance(child, ast.Attribute)
            else ""
        )
        if "test" in split_words(name):
            return True
    return False


def _best_comparisons(loop: ast.AST) -> list[ast.Compare]:
    """Comparisons in ``loop`` that involve a name like ``best_acc`` (keeping the best)."""
    return [
        node
        for node in ast.walk(loop)
        if isinstance(node, ast.Compare)
        and any(isinstance(n, ast.Name) and "best" in split_words(n.id) for n in ast.walk(node))
    ]


def _test_scored_names(loop: ast.AST) -> set[str]:
    """Names assigned in ``loop`` from a call on test-named data, e.g. ``acc = f(test_loader)``."""
    names: set[str] = set()
    for node in ast.walk(loop):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and _mentions_test(node.value)
        ):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def _selection_sites(source: SourceFile) -> list[int]:
    """Lines where a test-named set steers training or picks the best model."""
    assert source.tree is not None
    lines = [
        call.lineno
        for call in calls(source.tree)
        for kw in call.keywords
        if kw.arg in SELECTION_KEYWORDS and _mentions_test(kw.value)
    ]
    for loop in (n for n in ast.walk(source.tree) if isinstance(n, LOOPS)):
        scored = _test_scored_names(loop)
        for compare in _best_comparisons(loop):
            uses_score = any(
                isinstance(n, ast.Name) and n.id in scored for n in ast.walk(compare)
            ) or any(isinstance(n, ast.Call) and _mentions_test(n) for n in ast.walk(compare))
            if uses_score:
                lines.append(compare.lineno)
    return sorted(set(lines))


class TestSetSelection(Check):
    """The test set is used for early stopping or for picking the best epoch or model."""

    __test__ = False  # not a pytest test class, despite the name

    id: ClassVar[str] = "correctness.test-set-selection"
    title: ClassVar[str] = "The test set is used to choose the model"
    severity: ClassVar[Severity] = Severity.MAJOR
    dimension: ClassVar[Dimension] = Dimension.CORRECTNESS
    concept: ClassVar[str] = "Data leakage in evaluation"

    def run(self, project: Project) -> list[Finding]:
        """Flag test-named data in eval sets / early stopping, or scored inside a best-of loop."""
        locations = [
            source.location(line)
            for source in project.parsed
            if not source.is_test
            for line in _selection_sites(source)
        ]
        if not locations:
            return []
        message = (
            f"In {plural(len(locations), 'place')}, data named as the test set is used while "
            f"choosing the model: for early stopping, as an eval set, or scored inside a loop "
            f"that keeps the best epoch or setting. Then the test score is no longer an unseen "
            f"estimate; it was optimised, so it is too optimistic. Choose on a validation set "
            f"and touch the test set once, at the end. If this set is really a validation set, "
            f"rename it so the code says so."
        )
        return [self.finding(message, locations)]
