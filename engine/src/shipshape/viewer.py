"""Write a standalone HTML page that draws a report's architecture map.

This is a preview for the command line. The real interface comes with the web app.
"""

from __future__ import annotations

from importlib.resources import files

from shipshape.models import Report

PLACEHOLDER = "/*__REPORT__*/null"


def render_map_html(report: Report) -> str:
    """Return the viewer page with ``report`` embedded as JSON."""
    template = files("shipshape").joinpath("viewer_template.html").read_text(encoding="utf-8")
    # "</" inside the JSON would close the <script> tag early.
    payload = report.model_dump_json().replace("</", "<\\/")
    return template.replace(PLACEHOLDER, payload, 1)
