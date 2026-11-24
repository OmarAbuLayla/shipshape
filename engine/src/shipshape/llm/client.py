"""Talk to the LLM provider. DeepSeek speaks the OpenAI wire format.

Everything above this module depends only on :class:`ChatClient`, so tests can plug in a
fake and other providers can be added as one more class.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import openai

from shipshape.llm.settings import LLMSettings

Message = dict[str, str]


class LLMError(RuntimeError):
    """A call to the LLM failed; the message is safe to show (it never contains the key)."""


class FatalLLMError(LLMError):
    """A failure that will repeat for every request (bad key, no credit): stop the whole run."""


@dataclass(frozen=True)
class Completion:
    """The text of one answer plus what it cost in tokens."""

    text: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    seconds: float


class ChatClient(Protocol):
    """Anything that can answer a list of chat messages with JSON text."""

    model: str

    def complete(self, messages: Sequence[Message]) -> Completion:
        """Return the model's answer to ``messages``."""
        ...


def _translate(exc: openai.OpenAIError, settings: LLMSettings) -> LLMError:
    if isinstance(exc, openai.AuthenticationError):
        return FatalLLMError("The API key was rejected. Check DEEPSEEK_API_KEY in .env.")
    if isinstance(exc, openai.NotFoundError):
        return FatalLLMError(f"Model {settings.model!r} was not found. Check SHIPSHAPE_LLM_MODEL.")
    if isinstance(exc, openai.RateLimitError):
        return LLMError("Rate limited. Try again in a moment.")
    if isinstance(exc, openai.APIConnectionError):
        return LLMError(f"Could not reach {settings.base_url}. Check your connection.")
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code == 402:
            return FatalLLMError("Insufficient balance. Top up your DeepSeek account.")
        return LLMError(f"The API returned HTTP {exc.status_code}.")
    return LLMError(f"LLM call failed: {type(exc).__name__}")


class OpenAICompatibleClient:
    """DeepSeek (or any OpenAI-compatible endpoint) in JSON mode."""

    def __init__(self, settings: LLMSettings, timeout: float = 180.0, max_tokens: int = 8000):
        self.settings = settings
        self.model = settings.model
        self.max_tokens = max_tokens
        self._client = openai.OpenAI(
            api_key=settings.require_key(),
            base_url=settings.base_url,
            timeout=timeout,
            max_retries=2,
        )

    def complete(self, messages: Sequence[Message]) -> Completion:
        """Send ``messages`` and ask for a JSON object back."""
        started = time.perf_counter()
        payload: list[Any] = list(messages)
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=payload,
                response_format={"type": "json_object"},
                max_tokens=self.max_tokens,
            )
        except openai.OpenAIError as exc:
            raise _translate(exc, self.settings) from exc
        usage = response.usage
        return Completion(
            text=response.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            # DeepSeek reports its automatic prefix cache with this extra field.
            cached_input_tokens=int(getattr(usage, "prompt_cache_hit_tokens", 0) or 0),
            output_tokens=usage.completion_tokens if usage else 0,
            seconds=time.perf_counter() - started,
        )


@dataclass(frozen=True)
class PingResult:
    """Outcome of a minimal test request."""

    reply: str
    seconds: float
    input_tokens: int
    output_tokens: int


def ping(settings: LLMSettings, timeout: float = 60.0) -> PingResult:
    """Send one tiny request to confirm the key, model and network all work."""
    client = openai.OpenAI(
        api_key=settings.require_key(), base_url=settings.base_url, timeout=timeout, max_retries=1
    )
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=settings.model,
            messages=[{"role": "user", "content": "Reply with exactly one word: ok"}],
            max_tokens=512,
        )
    except openai.OpenAIError as exc:
        raise _translate(exc, settings) from exc
    usage = response.usage
    return PingResult(
        reply=(response.choices[0].message.content or "").strip(),
        seconds=time.perf_counter() - started,
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )
