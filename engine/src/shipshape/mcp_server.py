"""MCP server: Shipshape's tools for Claude Code (and other MCP clients), over stdio.

Start it with ``shipshape-mcp``. Every tool is read-only with respect to the scanned project;
only ``map`` writes a file, and by default outside the project.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from shipshape import __version__, assist

INSTRUCTIONS = """\
Shipshape reviews Python projects (often AI-written ones) the way a careful senior engineer \
would and never runs their code. Call `scan` with the project folder to get findings and a \
grade. Explain findings in the user's own code, and use `lesson` for the concept behind one. \
Before changing a file to fix a finding, pass your edits to `verify_fix`; apply \
them only if it says PASSED, and tell the user why it was rejected otherwise. Scan again after \
fixing to show the new grade."""

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

server = MCPServer(
    name="shipshape",
    title="Shipshape",
    version=__version__,
    instructions=INSTRUCTIONS,
)


@server.tool(annotations=READ_ONLY, structured_output=False)
def scan(path: str, max_findings: int = assist.DEFAULT_MAX_FINDINGS) -> str:
    """Scan a Python project folder (absolute path) and return its findings and grade.

    Findings are ordered most severe first. Each has a check id (needed for verify_fix),
    locations as path:line, a message, and the lesson that teaches the concept.
    """
    try:
        return assist.scan(path, max_findings)
    except assist.AssistError as exc:
        raise ToolError(str(exc)) from exc


@server.tool(annotations=READ_ONLY, structured_output=False)
def verify_fix(path: str, check_id: str, edits: list[assist.ProposedEdit]) -> str:
    """Check proposed edits for one finding in memory, without changing any file.

    Each edit targets a .py file (path relative to the project folder) and replaces either an
    exact ``search`` text that appears once in the file, or whole lines ``line`` to
    ``end_line`` as they are on disk now. Use line numbers to replace a line holding a secret
    without quoting it. Several edits to one file apply in order. The fix passes if every
    edited file still parses, the finding is gone from every place it was reported in the
    edited files, and no other check finds more problems there. Apply the edits yourself
    only after it passes.
    """
    try:
        return assist.verify_edits(path, check_id, edits)
    except assist.FixRejectedError as exc:
        return f"REJECTED: {exc}. Do not apply these edits; revise them or explain the fix."
    except assist.AssistError as exc:
        raise ToolError(str(exc)) from exc


@server.tool(annotations=READ_ONLY, structured_output=False)
def lesson(name: str = "") -> str:
    """The lesson behind a concept, by slug, concept name or check id; empty lists them all."""
    return assist.lesson(name)


@server.tool(
    name="map",
    annotations=ToolAnnotations(read_only_hint=False, open_world_hint=False),
    structured_output=False,
)
def map_page(path: str, output: str = "") -> str:
    """Write an interactive HTML map of the project's files, imports and findings.

    Returns the page's path. Without ``output`` it goes to the temporary folder, not the project.
    """
    try:
        return f"Map written to {assist.write_map(path, output)}. Open it in a browser."
    except assist.AssistError as exc:
        raise ToolError(str(exc)) from exc


def main() -> None:
    """Entry point of ``shipshape-mcp``: serve over stdio."""
    server.run("stdio")


if __name__ == "__main__":
    main()
