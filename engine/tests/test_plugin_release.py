"""The Claude Code plugin pins the engine to a tag that matches its own version."""

from __future__ import annotations

import json
import re

from .conftest import ENGINE_DIR

PLUGIN_DIR = ENGINE_DIR.parent / "plugin"


def test_plugin_engine_pin_matches_the_plugin_version() -> None:
    manifest = json.loads((PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    servers = json.loads((PLUGIN_DIR / ".mcp.json").read_text("utf-8"))["mcpServers"]
    source = " ".join(servers["shipshape"]["args"])
    pin = re.search(r"shipshape@v([0-9.]+)#subdirectory=engine", source)
    assert pin is not None, "the plugin must run a tagged engine, not main"
    assert pin.group(1) == manifest["version"], (
        "plugin.json version and the engine tag in .mcp.json differ; release both together "
        "(bump both, push, then tag the commit as v<version>)"
    )
