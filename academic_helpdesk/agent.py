"""The Academic Helpdesk agent graph.

`root_agent` is the module-level name that `adk web` and `adk run` discover.

    HelpdeskOrchestrator
      |-- policy_agent    rules, regulations, curriculum, credits, procedures
      |-- schedule_agent  slots, timetable, offering list, examination dates
      `-- email_agent     instructor contacts and email drafting

Set HELPDESK_SINGLE_AGENT=1 to load the baseline single-agent configuration
instead -- one agent with every tool and no delegation. The evaluation harness
uses this to compare the two architectures.
"""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from academic_helpdesk import config, prompts
from academic_helpdesk.llm_client import PatientLiteLLMClient
from academic_helpdesk.tools.contact_tools import lookup_course_instructor
from academic_helpdesk.tools.email_tools import draft_student_email
from academic_helpdesk.tools.escalation_tools import log_unanswered_question
from academic_helpdesk.tools.rag_tools import search_academic_documents
from academic_helpdesk.tools.schedule_tools import (
    check_slot_clash,
    find_courses,
    get_slot_timing,
    lookup_course,
)

APP_NAME = "academic_helpdesk"


def build_model(model_name: str | None = None) -> LiteLlm:
    """Build the LiteLLM wrapper for any provider LiteLLM supports.

    Local Ollama models need OLLAMA_API_BASE; hosted providers (Groq, OpenAI,
    Anthropic, ...) need their API key in the environment. We check the key here
    so a missing one surfaces as a clear setup error rather than a provider 401
    buried inside an agent turn.
    """
    name = model_name or config.CHAT_MODEL
    provider = name.split("/", 1)[0] if "/" in name else ""

    if provider.startswith("ollama"):
        os.environ.setdefault("OLLAMA_API_BASE", config.OLLAMA_HOST)
        return LiteLlm(model=name)

    key_env = config.PROVIDER_API_KEY_ENV.get(provider)
    if key_env and not os.environ.get(key_env):
        raise RuntimeError(
            f"Model '{name}' needs {key_env}, which is not set.\n"
            f"Put it in .env as {key_env}=... (see .env.example), or export it "
            f"in the shell.\n"
            "Hosted chat providers do not serve embeddings for this project's "
            "RAG, so also set EMBEDDING_BACKEND=local unless Ollama is running."
        )

    extra: dict = {"drop_params": True}
    if provider == "groq":
        # Groq's reasoning models (qwen3, gpt-oss) attach `reasoning_content` to
        # assistant turns. ADK round-trips that field back into the next
        # request's history, and Groq's own strict schema then rejects a
        # resubmitted assistant message that carries it -- a 400 on the second
        # turn of every conversation. reasoning_format="hidden" stops Groq from
        # emitting the field at all, which is the only real fix: drop_params
        # only strips unsupported *request* parameters, not fields already
        # baked into message history by the previous response.
        extra["reasoning_format"] = "hidden"
        # Free-tier Groq caps input tokens per minute, and a multi-agent turn makes
        # several model calls. This client waits as long as Groq asks, then retries.
        extra["llm_client"] = PatientLiteLLMClient()

    return LiteLlm(model=name, **extra)


def build_policy_agent(model: LiteLlm) -> LlmAgent:
    return LlmAgent(
        name="policy_agent",
        model=model,
        description=(
            "Academic rules and regulations, attendance, examinations and exam "
            "dates, the academic calendar, grading, makeup and leave policy, "
            "registration and add/drop, curriculum, credit and degree "
            "requirements, elective policy, circulars, fees and forms."
        ),
        instruction=prompts.POLICY_AGENT_INSTRUCTION,
        tools=[search_academic_documents, lookup_course, log_unanswered_question],
    )


def build_schedule_agent(model: LiteLlm) -> LlmAgent:
    return LlmAgent(
        name="schedule_agent",
        model=model,
        description=(
            "Timetable slots and timings, rooms, which courses are offered this "
            "semester, counts of courses or electives by department and level, "
            "and slot clashes."
        ),
        instruction=prompts.SCHEDULE_AGENT_INSTRUCTION,
        tools=[
            lookup_course,
            find_courses,
            get_slot_timing,
            check_slot_clash,
            search_academic_documents,
            log_unanswered_question,
        ],
    )


def build_email_agent(model: LiteLlm) -> LlmAgent:
    return LlmAgent(
        name="email_agent",
        model=model,
        description=(
            "Looks up a course instructor's contact details and drafts an email "
            "to the instructor for sick leave, a makeup examination or attendance "
            "condonation. Never sent."
        ),
        instruction=prompts.EMAIL_AGENT_INSTRUCTION,
        tools=[lookup_course_instructor, draft_student_email, log_unanswered_question],
    )


def build_multi_agent(model_name: str | None = None) -> LlmAgent:
    model = build_model(model_name)
    return LlmAgent(
        name="helpdesk_orchestrator",
        model=model,
        description="Routes academic helpdesk questions to the right specialist agent.",
        instruction=prompts.ORCHESTRATOR_INSTRUCTION,
        tools=[log_unanswered_question],
        sub_agents=[
            build_policy_agent(model),
            build_schedule_agent(model),
            build_email_agent(model),
        ],
    )


SINGLE_AGENT_INSTRUCTION = (
    "You are the IIT Jodhpur Academic Helpdesk. You answer questions about "
    "academic rules, curriculum, the timetable and the examination schedule, and "
    "you draft emails to course instructors.\n\n"
    + prompts.CONTEXT_BLOCK
    + "\nProcedure: use `search_academic_documents` for anything about rules, "
    "regulations, curriculum, procedure or exam dates; use `lookup_course`, "
    "`find_courses`, `get_slot_timing` and `check_slot_clash` for slots, "
    "offerings and counts, and report the tool's `match_count` "
    "verbatim; use `lookup_course_instructor` and then `draft_student_email` when "
    "the student wants an email. Never answer a factual question without first "
    "calling a tool.\n\n"
    + prompts.CITATION_BLOCK
    + "\n"
    + prompts.REFUSAL_BLOCK
)


def build_single_agent(model_name: str | None = None) -> LlmAgent:
    """Baseline configuration: one agent, all tools, no delegation."""
    return LlmAgent(
        name="academic_helpdesk_single",
        model=build_model(model_name),
        description="Single-agent baseline of the Academic Helpdesk.",
        instruction=SINGLE_AGENT_INSTRUCTION,
        tools=[
            search_academic_documents,
            lookup_course,
            find_courses,
            get_slot_timing,
            check_slot_clash,
            lookup_course_instructor,
            draft_student_email,
            log_unanswered_question,
        ],
    )


def build_agent(mode: str = "multi", model_name: str | None = None) -> LlmAgent:
    return build_single_agent(model_name) if mode == "single" else build_multi_agent(model_name)


root_agent = (
    build_single_agent()
    if os.environ.get("HELPDESK_SINGLE_AGENT") == "1"
    else build_multi_agent()
)
