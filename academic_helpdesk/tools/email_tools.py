"""Email drafting.

The draft is rendered from fixed templates by code rather than being improvised
by the model. That keeps every draft complete (recipient, subject, student
details, dates) and means it never quotes a rule, form or clause number: the
Institute's procedure is looked up in the documents, not asserted from a template.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from academic_helpdesk import config
from academic_helpdesk.tools.contact_tools import lookup_course_instructor

CC_LINE = "academic.section@iitj.ac.in; Faculty Advisor"

_REQUEST_TYPES = {"sick_leave", "makeup_exam", "attendance_condonation"}


def _parse_date(value: str) -> date | None:
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _pretty(value: str) -> str:
    parsed = _parse_date(value)
    return parsed.strftime("%d %B %Y") if parsed else (value or "<DATE>").strip()


def _day_count(from_date: str, to_date: str, fallback: int) -> int:
    start, end = _parse_date(from_date), _parse_date(to_date)
    if start and end and end >= start:
        return (end - start).days + 1
    return fallback


def _sick_leave_body(ctx: dict) -> str:
    return f"""Respected {ctx['instructor_name']},

I am {ctx['student_name']} (Roll No. {ctx['roll_number']}, {ctx['programme']}), registered for {ctx['course_code']} {ctx['course_title']} in {config.CURRENT_SEMESTER} of {config.CURRENT_ACADEMIC_YEAR}.

{ctx['reason_sentence']} I will therefore be unable to attend classes from {ctx['from_pretty']} to {ctx['to_pretty']} ({ctx['days']} day(s)), and I request you to kindly grant me leave for this period.

I will submit the supporting medical documentation on resuming classes, and I will catch up on the material covered during my absence.

Thank you for your consideration.

Respectfully,
{ctx['student_name']}
Roll No. {ctx['roll_number']}, {ctx['programme']}
{ctx['student_email']}"""


def _makeup_body(ctx: dict) -> str:
    return f"""Respected {ctx['instructor_name']},

I am {ctx['student_name']} (Roll No. {ctx['roll_number']}, {ctx['programme']}), registered for {ctx['course_code']} {ctx['course_title']}.

I was unable to appear in the {ctx['exam_type']} examination of this course held on {ctx['exam_pretty']} because of the following reason: {ctx['reason']}. The supporting certificate from the Institute Medical Centre is attached.

I request your recommendation on my application for a makeup examination. I will submit the application and the supporting certificate through the Academic Section as the Institute's procedure requires.

Thank you for your consideration.

Respectfully,
{ctx['student_name']}
Roll No. {ctx['roll_number']}, {ctx['programme']}
{ctx['student_email']}"""


def _condonation_body(ctx: dict) -> str:
    return f"""Respected {ctx['instructor_name']},

I am {ctx['student_name']} (Roll No. {ctx['roll_number']}, {ctx['programme']}). My attendance in {ctx['course_code']} {ctx['course_title']} currently stands at {ctx['attendance']}, which is below the 75% attendance the Institute expects.

The shortfall arose from the following reason: {ctx['reason']}, during {ctx['from_pretty']} to {ctx['to_pretty']}. The supporting documents are attached.

I request your support for my request for attendance condonation, which I will submit through the Academic Section.

Respectfully,
{ctx['student_name']}
Roll No. {ctx['roll_number']}, {ctx['programme']}
{ctx['student_email']}"""


def draft_student_email(
    request_type: str,
    course_code: str,
    reason: str,
    from_date: str,
    to_date: str,
    number_of_days: int,
    exam_type: str,
    exam_date: str,
    attendance_percent: str,
    student_name: str,
    roll_number: str,
    programme: str,
    student_email: str,
) -> dict:
    """Draft an email from the student to a course instructor, for the student to review.

    The draft is rendered from a fixed template, so it already contains the
    recipient, subject and student details, and it quotes no rule or form number.
    The email is NOT sent. Present the draft to the student and tell them to fill in
    any placeholder shown in angle brackets.

    Args:
        request_type: "sick_leave" for a leave intimation, "makeup_exam" for a
            missed examination, "attendance_condonation" for an attendance
            shortfall.
        course_code: The course code, for example "CSL7570".
        reason: The student's stated reason, for example "fever and throat
            infection". Pass an empty string if the student did not say.
        from_date: First day of absence, any common date format. Empty if unknown.
        to_date: Last day of absence. Empty if unknown.
        number_of_days: Number of days of leave requested; pass 0 if the student
            gave dates instead, and it will be computed.
        exam_type: For makeup requests: "Minor-1", "Minor-2" or "Major".
            Empty string otherwise.
        exam_date: For makeup requests, the date of the missed examination.
            Empty string otherwise.
        attendance_percent: For condonation requests, the student's current
            attendance, for example "68%". Empty string otherwise.
        student_name: Student's full name, or empty string to leave a placeholder.
        roll_number: Student's roll number, or empty string for a placeholder.
        programme: Student's programme, or empty string for a placeholder.
        student_email: Student's institute email, or empty string.

    Returns:
        A dict with "to", "cc", "subject", "body", "placeholders_to_fill" and
        "citations".
    """
    kind = (request_type or "").strip().lower()
    if kind not in _REQUEST_TYPES:
        return {
            "error": f"Unknown request_type '{request_type}'.",
            "allowed": sorted(_REQUEST_TYPES),
        }

    instructor = lookup_course_instructor(course_code)
    if not instructor.get("found"):
        return {
            "error": instructor.get("note", "Course not found."),
            "hint": "Confirm the course code with the student before drafting.",
        }

    days = _day_count(from_date, to_date, number_of_days or 0)
    reason_text = (reason or "").strip()

    ctx = {
        "instructor_name": instructor["instructor_name"],
        "course_code": instructor["course_code"],
        "course_title": instructor["course_title"],
        "student_name": student_name.strip() or "<STUDENT NAME>",
        "roll_number": roll_number.strip() or "<ROLL NUMBER>",
        "programme": programme.strip() or "<PROGRAMME>",
        "student_email": student_email.strip() or "<ROLL NUMBER>@iitj.ac.in",
        "reason": reason_text or "<REASON>",
        "reason_sentence": (
            f"I am unwell ({reason_text}) and have been advised rest."
            if reason_text
            else "I am unwell and have been advised rest."
        ),
        "from_pretty": _pretty(from_date) if from_date else "<FROM DATE>",
        "to_pretty": _pretty(to_date) if to_date else "<TO DATE>",
        "days": days if days > 0 else "<N>",
        "exam_type": (exam_type or "Major").strip(),
        "exam_pretty": _pretty(exam_date) if exam_date else "<EXAM DATE>",
        "attendance": (attendance_percent or "<ATTENDANCE>%").strip(),
    }

    if kind == "sick_leave":
        subject = (
            f"[{ctx['course_code']}] Sick leave request for {ctx['days']} day(s): "
            f"{ctx['from_pretty']} to {ctx['to_pretty']}"
        )
        body = _sick_leave_body(ctx)
        citations = [
            "Sick-leave email template (generated by the helpdesk, not an Institute form)",
            "faculty.csv -- faculty directory",
        ]
    elif kind == "makeup_exam":
        subject = (
            f"[{ctx['course_code']}] Request for Makeup {ctx['exam_type']} examination "
            f"-- missed on {ctx['exam_pretty']}"
        )
        body = _makeup_body(ctx)
        citations = [
            "Makeup-exam email template (generated by the helpdesk, not an Institute form)",
            "faculty.csv -- faculty directory",
        ]
    else:
        subject = f"[{ctx['course_code']}] Request for attendance condonation"
        body = _condonation_body(ctx)
        citations = [
            "Attendance-condonation email template (generated by the helpdesk, not an Institute form)",
            "faculty.csv -- faculty directory",
        ]

    full = f"{subject}\n{body}"
    placeholders = sorted({tok for tok in _extract_placeholders(full)})

    draft = {
        "to": instructor["instructor_email"],
        "cc": CC_LINE,
        "subject": subject,
        "body": f"{body}\n\nCc: {CC_LINE}",
        "instructor_name": ctx["instructor_name"],
        "request_type": kind,
        "placeholders_to_fill": placeholders,
        "citations": citations,
        "status": "draft_not_sent",
    }
    _append_jsonl(config.EMAIL_DRAFTS_LOG, draft)
    return draft


def _extract_placeholders(text: str) -> list[str]:
    out, buffer, inside = [], "", False
    for ch in text:
        if ch == "<":
            inside, buffer = True, ""
        elif ch == ">" and inside:
            if buffer:
                out.append(f"<{buffer}>")
            inside = False
        elif inside:
            buffer += ch
    return out


def _append_jsonl(path, payload: dict) -> None:
    record = {"timestamp": datetime.now().isoformat(timespec="seconds"), **payload}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
