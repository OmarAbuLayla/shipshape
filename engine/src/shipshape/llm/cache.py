"""On-disk cache of finished explanations, so re-scanning unchanged code costs nothing.

Keys hash everything that affects the answer: prompt version, model, the finding and the code
that was shown. Values are the final, validated explanations (secrets are already redacted).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from pydantic import ValidationError

from shipshape.llm.prompts import PROMPT_VERSION
from shipshape.models import Explanation


def default_cache_dir() -> Path:
    """``SHIPSHAPE_CACHE_DIR`` or ``~/.shipshape/cache/explanations``."""
    override = os.environ.get("SHIPSHAPE_CACHE_DIR")
    return Path(override) if override else Path.home() / ".shipshape" / "cache" / "explanations"


def cache_key(model: str, check_id: str, fix_allowed: bool, context_text: str) -> str:
    """Stable hash of every input that shapes the answer."""
    material = "\n".join([PROMPT_VERSION, model, check_id, str(fix_allowed), context_text])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class ExplanationCache:
    """A folder of ``<key>.json`` files. Unreadable entries are treated as misses."""

    def __init__(self, directory: Path | None = None, enabled: bool = True) -> None:
        self.directory = directory or default_cache_dir()
        self.enabled = enabled

    def get(self, key: str) -> Explanation | None:
        """Return the cached explanation, or ``None``."""
        if not self.enabled:
            return None
        path = self.directory / f"{key}.json"
        try:
            return Explanation.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
            return None

    def put(self, key: str, explanation: Explanation) -> None:
        """Store an explanation; failures to write are ignored (the cache is an optimisation)."""
        if not self.enabled:
            return
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            (self.directory / f"{key}.json").write_text(
                explanation.model_dump_json(), encoding="utf-8"
            )
        except OSError:
            pass
