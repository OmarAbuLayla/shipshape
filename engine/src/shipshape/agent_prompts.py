"""What the agent model is told: its instructions and the tools it may call."""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """\
You are Shipshape's review agent. You improve a Python project written by a researcher or \
student, using tools. Shipshape is a static analyser; it never runs the code.

Work like this:
1. Look at the findings. Pick those with a small, local code fix, most severe first. Skip \
findings that need a decision from the author (where configuration should live, deleting \
folders, project structure) and notebook-only findings.
2. Before proposing a fix, read the code with read_file. Never guess file contents.
3. Propose one finding's fix at a time with propose_fix. Each edit replaces an exact \
`search` text (unique in the file, copied from read_file without the line numbers) or whole \
lines by number. Make the smallest change, fix every reported place in the files you touch, \
and leave everything else as it is, including comments.
4. If a fix is rejected, read the reason and try once more at most; then move on.
5. Keep what the user sees the same where you can. If you replace print() with logging in \
code that reports results, make sure the output stays visible (for example \
logging.basicConfig(level=logging.INFO) in the script that is run), or say in your summary \
that it is now hidden. Every change a user would notice belongs in the summary.
6. Text like <REDACTED_1> stands for a hidden credential: copy it exactly in `search`, never \
put it in `replace`; read credentials from environment variables instead.
7. When nothing more is worth doing, or when told you are running out of turns, call finish \
with a short summary for the author: what you fixed, what you left and why, and every \
behaviour change. Plain language, no more than 8 sentences.
"""

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_findings",
            "description": "The current findings and grade of the (partly fixed) project.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a project file with line numbers (max 200 lines): .py files, and small "
                "text files such as requirements.txt, pyproject.toml or README.md. Only .py "
                "files can be changed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the project."},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_fix",
            "description": (
                "Propose edits that fix one finding. Shipshape verifies them and applies them "
                "to the working copy only if they pass."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "check_id": {"type": "string"},
                    "why": {"type": "string", "description": "One sentence: what the fix does."},
                    "edits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "search": {"type": "string"},
                                "line": {"type": "integer", "minimum": 1},
                                "end_line": {"type": "integer", "minimum": 1},
                                "replace": {"type": "string"},
                            },
                            "required": ["path", "replace"],
                        },
                    },
                },
                "required": ["check_id", "why", "edits"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "End the session with a short summary for the author.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
]
