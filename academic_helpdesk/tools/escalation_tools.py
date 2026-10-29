"""Logging of questions the helpdesk could not answer, for referral to a human."""

from __future__ import annotations

import json
from datetime import datetime

from academic_helpdesk import config

REASONS = {
    "out_of_scope": "Not an academic matter the helpdesk covers (campus life, travel, food, hostels, fees of third parties, personal advice).",
    "no_supporting_document": "An academic question, but no document in the corpus covers it.",
    "needs_personal_record": "Requires the student's own record, which the helpdesk cannot access.",
    "ambiguous": "The question is too ambiguous to answer without clarification.",
}


def log_unanswered_question(question: str, reason_code: str, notes: str) -> dict:
    """Record a question the helpdesk could not answer, so a human can follow up.

    Call this EVERY time you refuse to answer, immediately before telling the
    student that you do not know.

    Args:
        question: The student's question, as asked.
        reason_code: One of "out_of_scope", "no_supporting_document",
            "needs_personal_record", "ambiguous".
        notes: A short note on what was searched or what is missing.

    Returns:
        A dict confirming the log entry and the referral route.
    """
    code = (reason_code or "").strip().lower()
    if code not in REASONS:
        code = "out_of_scope"

    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "question": (question or "").strip(),
        "reason_code": code,
        "reason": REASONS[code],
        "notes": (notes or "").strip(),
        "status": "pending_human_review",
    }
    with config.UNANSWERED_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {
        "logged": True,
        "reason": REASONS[code],
        "referral": "Referred to the Academic Section (academic.section@iitj.ac.in) for a human response.",
        "log_file": str(config.UNANSWERED_LOG),
    }


def read_unanswered_log(limit: int) -> dict:
    """Read back the log of unanswered questions. Intended for staff review, not for students.

    Args:
        limit: Maximum number of most recent entries to return; 0 means all.

    Returns:
        A dict with "entries" and "total".
    """
    if not config.UNANSWERED_LOG.exists():
        return {"entries": [], "total": 0}

    lines = [
        json.loads(line)
        for line in config.UNANSWERED_LOG.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    entries = lines[-limit:] if limit and limit > 0 else lines
    return {"entries": entries, "total": len(lines)}
