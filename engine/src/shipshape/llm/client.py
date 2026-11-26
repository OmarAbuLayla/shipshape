"""Talk to the LLM provider over the OpenAI wire format (DeepSeek, OpenAI and compatibles).

Everything above this module depends only on :class:`ChatClient`, so tests can plug in a
fake and other providers can be added as one more class.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict

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


@dataclass(frozen=True)
class ToolCall:
    """One tool the model wants to run: its id, name and JSON-encoded arguments."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolTurn:
    """One answer in a tool-using conversation: text, tool calls, or both, plus its cost."""

    text: str
    tool_calls: tuple[ToolCall, ...]
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


class ToolChatClient(Protocol):
    """Anything that can continue a conversation in which the model may call tools."""

    model: str

    def complete_tools(
        self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> ToolTurn:
        """Return the model's next turn; ``tools`` are OpenAI-style function definitions."""
        ...


class ChatClient(Protocol):
    """Anything that can answer a list of chat messages with JSON text."""

    model: str

    def complete(self, messages: Sequence[Message]) -> Completion:
        """Return the model's answer to ``messages``."""
        ...


def _translate(exc: openai.OpenAIError, settings: LLMSettings) -> LLMError:
    if isinstance(exc, openai.AuthenticationError):
        return FatalLLMError(f"The API key was rejected. Check {settings.key_var} in .env.")
    if isinstance(exc, openai.NotFoundError):
        return FatalLLMError(f"Model {settings.model!r} was not found. Check SHIPSHAPE_LLM_MODEL.")
    if isinstance(exc, openai.RateLimitError):
        return LLMError("Rate limited. Try again in a moment.")
    if isinstance(exc, openai.APIConnectionError):
        return LLMError(f"Could not reach {settings.base_url}. Check your connection.")
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code == 402:
            return FatalLLMError(f"Insufficient balance. Top up your {settings.provider} account.")
        return LLMError(f"The API returned HTTP {exc.status_code}.")
    return LLMError(f"LLM call failed: {type(exc).__name__}")


class _Limit(TypedDict, total=False):
    max_tokens: int
    max_completion_tokens: int


def _limit(settings: LLMSettings, tokens: int) -> _Limit:
    """Cap the answer at ``tokens`` under the field name this provider expects."""
    if settings.token_limit == "max_completion_tokens":
        return {"max_completion_tokens": tokens}
    return {"max_tokens": tokens}


def _cached_tokens(usage: object) -> int:
    """Input tokens served from the provider's prompt cache, in either common format."""
    # DeepSeek reports its prefix cache with an extra field; OpenAI and most others nest it.
    deepseek = getattr(usage, "prompt_cache_hit_tokens", None)
    if deepseek:
        return int(deepseek)
    details = getattr(usage, "prompt_tokens_details", None)
    return int(getattr(details, "cached_tokens", 0) or 0)


class OpenAICompatibleClient:
    """Any OpenAI-compatible endpoint (DeepSeek, OpenAI, OpenRouter, Ollama, ...) in JSON mode."""

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
                **_limit(self.settings, self.max_tokens),
            )
        except openai.OpenAIError as exc:
            raise _translate(exc, self.settings) from exc
        usage = response.usage
        return Completion(
            text=response.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            cached_input_tokens=_cached_tokens(usage),
            output_tokens=usage.completion_tokens if usage else 0,
            seconds=time.perf_counter() - started,
        )

    def complete_tools(
        self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> ToolTurn:
        """Continue a conversation in which the model may call ``tools`` (function calling)."""
        payload: list[Any] = list(messages)
        tool_list: list[Any] = list(tools)
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=payload,
                tools=tool_list,
                **_limit(self.settings, self.max_tokens),
            )
        except openai.OpenAIError as exc:
            raise _translate(exc, self.settings) from exc
        message = response.choices[0].message
        usage = response.usage
        found: list[ToolCall] = []
        for call in message.tool_calls or ():
            function = getattr(call, "function", None)  # custom (non-function) tools are ignored
            if function is not None:
                found.append(ToolCall(call.id, function.name, function.arguments or "{}"))
        calls = tuple(found)
        return ToolTurn(
            text=message.content or "",
            tool_calls=calls,
            input_tokens=usage.prompt_tokens if usage else 0,
            cached_input_tokens=_cached_tokens(usage),
            output_tokens=usage.completion_tokens if usage else 0,
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
            **_limit(settings, 512),
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
