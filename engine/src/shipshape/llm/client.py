"""Thin wrapper around the provider's API. DeepSeek speaks the OpenAI wire format."""

from __future__ import annotations

import time
from dataclasses import dataclass

import openai

from shipshape.llm.settings import LLMSettings


class LLMError(RuntimeError):
    """A call to the LLM failed; the message is safe to show (it never contains the key)."""


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
    except openai.AuthenticationError as exc:
        raise LLMError("The API key was rejected. Check DEEPSEEK_API_KEY in .env.") from exc
    except openai.NotFoundError as exc:
        raise LLMError(
            f"Model {settings.model!r} was not found. Check SHIPSHAPE_LLM_MODEL."
        ) from exc
    except openai.RateLimitError as exc:
        raise LLMError("Rate limited or out of credit. Check your balance and try again.") from exc
    except openai.APIConnectionError as exc:
        raise LLMError(f"Could not reach {settings.base_url}. Check your connection.") from exc
    except openai.APIStatusError as exc:
        if exc.status_code == 402:
            raise LLMError("Insufficient balance. Top up your DeepSeek account.") from exc
        raise LLMError(f"The API returned HTTP {exc.status_code}.") from exc
    usage = response.usage
    return PingResult(
        reply=(response.choices[0].message.content or "").strip(),
        seconds=time.perf_counter() - started,
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )
