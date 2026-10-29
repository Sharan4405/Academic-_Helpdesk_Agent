"""Interactive terminal client.

    python -m academic_helpdesk.cli
    python -m academic_helpdesk.cli --mode single --model ollama_chat/llama3.1:8b
    python -m academic_helpdesk.cli --ask "What is the slot for Autonomous Systems?"
"""

from __future__ import annotations

import argparse
import asyncio

from academic_helpdesk import config
from academic_helpdesk.rag.store import get_collection
from academic_helpdesk.runner import HelpdeskSession

BANNER = """\
IIT Jodhpur Academic Helpdesk -- {mode} agent, model {model}
Ask about rules, curriculum, slots, exam dates, or ask for an email draft.
Type 'exit' to quit, 'trace' to see the tool calls behind the last answer.
"""


def _check_index() -> bool:
    try:
        count = get_collection().count()
    except Exception as exc:
        print(f"Cannot open the vector store: {exc}")
        return False
    if count == 0:
        print("Vector store is empty. Run: python -m academic_helpdesk.rag.ingest")
        return False
    print(f"Vector store: {count} chunks indexed.")
    return True


def _print_trace(turn) -> None:
    if turn.error:
        print(f"  error: {turn.error}")
    print(f"  agents: {' -> '.join(turn.agents_involved) or '(none)'}")
    for call in turn.tool_calls:
        args = ", ".join(f"{k}={v!r}" for k, v in call["args"].items() if v not in ("", 0))
        print(f"  tool: {call['by']} -> {call['name']}({args})")
    if turn.retrieved_doc_ids:
        print(f"  documents retrieved: {', '.join(turn.retrieved_doc_ids)}")


async def _run(args: argparse.Namespace) -> int:
    if not _check_index():
        return 1

    session = HelpdeskSession(mode=args.mode, model_name=args.model)

    if args.ask:
        turn = await session.ask(args.ask)
        print(f"\n{turn.answer}\n")
        if args.trace:
            _print_trace(turn)
        return 0

    print(BANNER.format(mode=args.mode, model=args.model or config.CHAT_MODEL))
    last = None
    while True:
        try:
            question = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            return 0
        if question.lower() == "trace":
            if last:
                _print_trace(last)
            else:
                print("  nothing asked yet")
            continue

        last = await session.ask(question)
        print(f"\nhelpdesk > {last.answer}\n")
        if args.trace:
            _print_trace(last)


def main() -> int:
    parser = argparse.ArgumentParser(description="Academic Helpdesk CLI")
    parser.add_argument("--mode", choices=["multi", "single"], default="multi")
    parser.add_argument("--model", default=None, help="LiteLLM model string")
    parser.add_argument("--ask", default=None, help="ask one question and exit")
    parser.add_argument("--trace", action="store_true", help="show tool calls")
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
