"""Route a command name to an exit code."""

from __future__ import annotations


def route(command: str, verbose: bool = False) -> int:
    """Map a command to an exit code (deliberately one long branch chain)."""
    if command == "train":
        code = 1
    elif command == "test":
        code = 2
    elif command == "eval":
        code = 3
    elif command == "export":
        code = 4
    elif command == "plot":
        code = 5
    elif command == "clean":
        code = 6
    elif command == "download":
        code = 7
    elif command == "upload":
        code = 8
    elif command == "sync":
        code = 9
    elif command == "report":
        code = 10
    elif command == "profile":
        code = 11
    elif command == "lint":
        code = 12
    elif command == "format":
        code = 13
    elif command == "deploy":
        code = 14
    elif command == "rollback":
        code = 15
    elif command == "status":
        code = 16
    else:
        code = 0
    if verbose and code > 5:
        code += 100
    return code
