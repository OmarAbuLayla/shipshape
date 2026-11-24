"""Read LLM settings from the environment and a ``.env`` file.

Real environment variables win over ``.env``, so CI or a shell can override the file.
The API key is never printed or logged; use :meth:`LLMSettings.key_status` to talk about it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import find_dotenv, load_dotenv

# Every provider speaks the OpenAI chat-completions format and must support JSON mode.
# An empty default means the user has to set it. OpenAI's newer models only accept
# ``max_completion_tokens``; most other services still expect ``max_tokens``.
SUPPORTED_PROVIDERS: dict[str, dict[str, str]] = {
    "deepseek": {
        "key_var": "DEEPSEEK_API_KEY",
        "base_url_var": "DEEPSEEK_BASE_URL",
        "default_base_url": "https://api.deepseek.com",
        "default_model": "deepseek-flash",
        "token_limit": "max_tokens",
    },
    "openai": {
        "key_var": "OPENAI_API_KEY",
        "base_url_var": "OPENAI_BASE_URL",
        "default_base_url": "https://api.openai.com/v1",
        "default_model": "",
        "token_limit": "max_completion_tokens",
    },
    # Anything else with an OpenAI-compatible endpoint: OpenRouter, Mistral, Groq,
    # Together, a local Ollama or vLLM server, ...
    "openai-compatible": {
        "key_var": "SHIPSHAPE_LLM_API_KEY",
        "base_url_var": "SHIPSHAPE_LLM_BASE_URL",
        "default_base_url": "",
        "default_model": "",
        "token_limit": "max_tokens",
    },
}


# USD per 1M tokens at DeepSeek's peak rates (off-peak is half), from their pricing page
# in November 2026: (input cache miss, input cache hit, output). Used only for estimates.
PRICES_PER_MILLION: dict[str, tuple[float, float, float]] = {
    "deepseek-flash": (0.30, 0.006, 1.20),
    "deepseek-v4-pro": (1.32, 0.044, 3.96),
}


def estimate_cost(model: str, input_tokens: int, cached_input: int, output: int) -> float | None:
    """Upper-bound cost in USD at peak prices, or ``None`` for a model without a price."""
    prices = PRICES_PER_MILLION.get(model)
    if prices is None:
        return None
    miss, hit, out = prices
    uncached = max(input_tokens - cached_input, 0)
    return (uncached * miss + cached_input * hit + output * out) / 1_000_000


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
    token_limit: str = "max_tokens"  # the request field that caps the answer's length

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
    if not model:
        raise SettingsError(f"Set SHIPSHAPE_LLM_MODEL to the model {provider} should use.")
    base_url = os.environ.get(spec["base_url_var"], "").strip() or spec["default_base_url"]
    if not base_url:
        raise SettingsError(
            f"Set {spec['base_url_var']} to the service's OpenAI-compatible endpoint "
            "(for example https://openrouter.ai/api/v1 or http://localhost:11434/v1)."
        )
    api_key = os.environ.get(spec["key_var"], "").strip() or None
    return LLMSettings(
        provider,
        model,
        base_url,
        spec["key_var"],
        api_key,
        env_file or None,
        spec["token_limit"],
    )
