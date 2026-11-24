"""Read LLM settings from the environment and a ``.env`` file.

Real environment variables win over ``.env``, so CI or a shell can override the file.
The API key is never printed or logged; use :meth:`LLMSettings.key_status` to talk about it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import find_dotenv, load_dotenv

SUPPORTED_PROVIDERS: dict[str, dict[str, str]] = {
    "deepseek": {
        "key_var": "DEEPSEEK_API_KEY",
        "base_url_var": "DEEPSEEK_BASE_URL",
        "default_base_url": "https://api.deepseek.com",
        "default_model": "deepseek-flash",
    },
}


class SettingsError(ValueError):
    """The LLM configuration is missing or invalid."""


@dataclass(frozen=True)
class LLMSettings:
    """Which provider and model to call, and with which credentials."""

    provider: str
    model: str
    base_url: str
    key_var: str
    api_key: str | None
    env_file: str | None = None  # the .env that was read, if any

    def key_status(self) -> str:
        """Describe the key without revealing any part of it."""
        if not self.api_key:
            return f"missing (set {self.key_var} in .env or your environment)"
        return f"set ({len(self.api_key)} characters)"

    def require_key(self) -> str:
        """Return the key, or raise with instructions if it is missing."""
        if not self.api_key:
            raise SettingsError(
                f"No API key: set {self.key_var} in the .env file at the project root "
                f"(copy .env.example) or in your environment."
            )
        return self.api_key


def load_settings(*, read_dotenv: bool = True) -> LLMSettings:
    """Build settings from ``SHIPSHAPE_LLM_*`` and the provider's own variables."""
    env_file = find_dotenv(usecwd=True) if read_dotenv else ""
    if env_file:
        load_dotenv(env_file, override=False)
    provider = os.environ.get("SHIPSHAPE_LLM_PROVIDER", "deepseek").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_PROVIDERS))
        raise SettingsError(f"Unknown provider {provider!r}. Supported: {supported}.")
    spec = SUPPORTED_PROVIDERS[provider]
    model = os.environ.get("SHIPSHAPE_LLM_MODEL", "").strip() or spec["default_model"]
    base_url = os.environ.get(spec["base_url_var"], "").strip() or spec["default_base_url"]
    api_key = os.environ.get(spec["key_var"], "").strip() or None
    return LLMSettings(provider, model, base_url, spec["key_var"], api_key, env_file or None)
