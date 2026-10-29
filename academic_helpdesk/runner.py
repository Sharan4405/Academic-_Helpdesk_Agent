"""Programmatic and interactive drivers for the helpdesk agent."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from academic_helpdesk.agent import APP_NAME, build_agent


@dataclass
class Turn:
    """What the agent said, plus the trace needed to score groundedness."""

    answer: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    agents_involved: list[str] = field(default_factory=list)
    retrieved_doc_ids: list[str] = field(default_factory=list)
    intermediate_text: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def delegated_to(self) -> str:
        for call in self.tool_calls:
            if call["name"] == "transfer_to_agent":
                return str(call["args"].get("agent_name", ""))
        return ""

    @property
    def tool_names(self) -> list[str]:
        return [c["name"] for c in self.tool_calls]


class HelpdeskSession:
    """One conversation with the agent. Reuse it to ask follow-up questions."""

    def __init__(self, mode: str = "multi", model_name: str | None = None):
        self.mode = mode
        self.agent = build_agent(mode=mode, model_name=model_name)
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            app_name=APP_NAME, agent=self.agent, session_service=self.session_service
        )
        self.user_id = "student"
        self.session_id = f"s-{uuid.uuid4().hex[:12]}"
        self._started = False

    async def _ensure_session(self) -> None:
        if not self._started:
            await self.session_service.create_session(
                app_name=APP_NAME, user_id=self.user_id, session_id=self.session_id
            )
            self._started = True

    async def ask(self, question: str) -> Turn:
        await self._ensure_session()
        turn = Turn()
        message = types.Content(role="user", parts=[types.Part(text=question)])

        try:
            async for event in self.runner.run_async(
                user_id=self.user_id, session_id=self.session_id, new_message=message
            ):
                if event.author and event.author not in turn.agents_involved:
                    turn.agents_involved.append(event.author)

                if not event.content or not event.content.parts:
                    continue

                for part in event.content.parts:
                    if getattr(part, "function_call", None):
                        turn.tool_calls.append(
                            {
                                "name": part.function_call.name,
                                "args": dict(part.function_call.args or {}),
                                "by": event.author or "",
                            }
                        )
                    if getattr(part, "function_response", None):
                        turn.retrieved_doc_ids.extend(
                            _doc_ids(part.function_response.response)
                        )
                    if getattr(part, "text", None):
                        text = part.text.strip()
                        if not text:
                            continue
                        if event.is_final_response():
                            turn.answer = text
                        else:
                            turn.intermediate_text.append(text)
        except Exception as exc:  # a local 8B model can emit malformed tool calls
            turn.error = f"{type(exc).__name__}: {exc}"

        if not turn.answer and turn.intermediate_text:
            turn.answer = turn.intermediate_text[-1]

        seen: set[str] = set()
        turn.retrieved_doc_ids = [
            d for d in turn.retrieved_doc_ids if not (d in seen or seen.add(d))
        ]
        return turn


def _doc_ids(response: object) -> list[str]:
    """Pull doc_id values out of a tool response of arbitrary shape."""
    found: list[str] = []
    if isinstance(response, dict):
        for key, value in response.items():
            if key == "doc_id" and isinstance(value, str) and value:
                found.append(value)
            else:
                found.extend(_doc_ids(value))
    elif isinstance(response, (list, tuple)):
        for item in response:
            found.extend(_doc_ids(item))
    return found


async def ask_once(question: str, mode: str = "multi", model_name: str | None = None) -> Turn:
    """Fresh session, one question. Used by the evaluation harness."""
    return await HelpdeskSession(mode=mode, model_name=model_name).ask(question)
