"""Turn a Jupyter notebook into analysable Python source.

Code cells are concatenated into one text. IPython magics and shell escapes are blanked
(not removed) so line numbers stay stable, and cells that do not parse on their own are
blanked too, so one broken cell does not hide the rest of the notebook from analysis.
"""

from __future__ import annotations

import ast
import json
import warnings


class NotebookError(ValueError):
    """The file is not a readable notebook."""


def _cell_source(cell: dict[str, object]) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(str(part) for part in source)
    return str(source)


def _clean_cell(lines: list[str]) -> list[str]:
    if lines and lines[0].lstrip().startswith("%%"):
        return ["" for _ in lines]
    cleaned = ["" if line.lstrip().startswith(("%", "!")) else line for line in lines]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ast.parse("\n".join(cleaned))
    except (SyntaxError, ValueError):
        return ["" for _ in cleaned]
    return cleaned


def notebook_to_source(raw: str) -> tuple[str, tuple[int, ...]]:
    """Return the notebook's code as one text, plus the 1-based start line of each code cell."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NotebookError(f"Invalid notebook JSON: {exc}") from exc
    cells = data.get("cells") if isinstance(data, dict) else None
    if not isinstance(cells, list):
        raise NotebookError("Notebook has no 'cells' list")

    lines: list[str] = []
    starts: list[int] = []
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        cell_lines = _clean_cell(_cell_source(cell).splitlines()) or [""]
        starts.append(len(lines) + 1)
        lines.extend(cell_lines)
    return "\n".join(lines) + "\n", tuple(starts)
