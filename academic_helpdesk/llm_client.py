"""A LiteLLM client that waits out provider rate limits instead of failing the turn.

Groq's free tier caps input tokens per minute (about 7-8k). One multi-agent turn
makes several model calls, each re-sending the instructions, tool schemas and
retrieved passages, so a turn can exceed the cap even though no single request
does. The 429 body says exactly how long to wait ("Please try again in 17.1s"),
so we sleep that long and retry the same call; the turn then completes, just
slower. LiteLLM's own retries fire within a second or two, which only burns more
of the same minute's budget.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections.abc import Callable
from contextvars import ContextVar

from google.adk.models.lite_llm import LiteLLMClient

RETRY_HINT = re.compile(r"try again in\s*(?:(\d+)m(?!s))?\s*(\d+(?:\.\d+)?)\s*(ms|s)", re.IGNORECASE)
MAX_WAIT_SECONDS = 90.0

# A caller (the web service) can set this to learn about waits as they start.
rate_limit_callback: ContextVar[Callable[[float], None] | None] = ContextVar(
    "rate_limit_callback", default=None
)


def _wait_hint(message: str) -> float | None:
    """Seconds Groq asks us to wait: handles "17.1s", "1m4.2s" and "622.5ms"."""
    match = RETRY_HINT.search(message)
    if not match:
        return None
    minutes, amount, unit = match.groups()
    seconds = float(amount) / 1000 if unit.lower() == "ms" else float(amount)
    return float(minutes or 0) * 60 + seconds


class PatientLiteLLMClient(LiteLLMClient):
    def __init__(self, attempts: int = 8):
        super().__init__()
        self.attempts = attempts

    async def acompletion(self, model, messages, tools, **kwargs):
        import litellm

        if os.environ.get("HELPDESK_LOG_TOKENS"):
            # Rough size of this request (about 3.6 characters per token), to see
            # where a turn's token budget goes.
            body = len(json.dumps(messages, default=str))
            schema = len(json.dumps(tools, default=str)) if tools else 0
            print(
                f"  [llm call: ~{int((body + schema) / 3.6)} tokens "
                f"(messages {int(body / 3.6)}, tool schemas {int(schema / 3.6)})]",
                file=sys.stderr,
                flush=True,
            )
        for attempt in range(1, self.attempts + 1):
            try:
                return await super().acompletion(model, messages, tools, **kwargs)
            except litellm.RateLimitError as exc:
                wait = _wait_hint(str(exc))
                if wait is None or attempt == self.attempts:
                    raise
                wait = min(wait + 1.0, MAX_WAIT_SECONDS)
                print(
                    f"  [rate limited by provider; waiting {wait:.0f}s "
                    f"(attempt {attempt}/{self.attempts})]",
                    file=sys.stderr,
                    flush=True,
                )
                if (notify := rate_limit_callback.get()) is not None:
                    notify(wait)
                await asyncio.sleep(wait)
        raise RuntimeError("unreachable")
