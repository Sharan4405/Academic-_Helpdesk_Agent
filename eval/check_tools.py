"""Self-test of the deterministic layer: CSV tools, chunking and email drafting.

Runs without Ollama and without an LLM, so it can verify the ground truth behind
the evaluation set before spending time on model runs.

    python eval/check_tools.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from academic_helpdesk import config  # noqa: E402
from academic_helpdesk.rag.chunking import chunk_corpus  # noqa: E402
from academic_helpdesk.tools import catalogue  # noqa: E402
from academic_helpdesk.tools.contact_tools import lookup_course_instructor  # noqa: E402
from academic_helpdesk.tools.email_tools import draft_student_email  # noqa: E402
from academic_helpdesk.tools.escalation_tools import log_unanswered_question  # noqa: E402
from academic_helpdesk.tools.schedule_tools import (  # noqa: E402
    check_slot_clash,
    find_courses,
    get_slot_timing,
    lookup_course,
    lookup_exam_schedule,
)

failures: list[str] = []


def check(label: str, actual, expected) -> None:
    if actual == expected:
        print(f"  ok   {label}: {actual!r}")
    else:
        print(f"  FAIL {label}: got {actual!r}, expected {expected!r}")
        failures.append(label)


def main() -> int:
    print("Corpus")
    documents = sorted(config.DOCUMENTS_DIR.glob("*.md"))
    chunks = chunk_corpus()
    print(f"  {len(documents)} documents -> {len(chunks)} chunks")
    check("every chunk carries a doc_id", all(c.metadata["doc_id"] for c in chunks), True)
    check(
        "front matter parsed for every document",
        len({c.metadata["doc_id"] for c in chunks}),
        len(documents),
    )

    print("\nStructured data")
    check("courses loaded", len(catalogue.courses()) > 40, True)
    check("instructors loaded", len(catalogue.instructors()) > 20, True)
    orphans = [
        r["course_code"]
        for r in catalogue.courses()
        if catalogue.instructor_by_id(r["instructor_id"]) is None
    ]
    check("no course points at a missing instructor", orphans, [])
    unknown_slots = sorted(
        {
            r["slot"]
            for r in catalogue.courses()
            if r["slot"] not in {s["slot_code"] for s in catalogue.slots()}
        }
    )
    check("every course slot exists in the timetable", unknown_slots, [])

    print("\nQ12 slot of Autonomous Systems")
    result = lookup_course("Autonomous Systems")
    codes = sorted(m["course_code"] for m in result["matches"])
    check("matches", codes, ["CSL7620", "CSP7620"])
    lecture = next(m for m in result["matches"] if m["course_code"] == "CSL7620")
    check("slot", lecture["slot"], "G")
    check(
        "timings",
        lecture["slot_timings"],
        ["Tuesday 11:00-12:30", "Thursday 11:00-12:30"],
    )
    check("credits", lecture["credits"], 4)
    check("ltp", lecture["ltp"], "3-0-2")

    print("\nQ13 400-level Humanities electives")
    hss = find_courses("Humanities", 400, "elective", "")
    check("count", hss["match_count"], 4)
    check(
        "codes",
        sorted(m["course_code"] for m in hss["matches"]),
        ["HSL4010", "HSL4110", "HSL4220", "HSL4330"],
    )
    check(
        "department normalised",
        hss["filters_applied"]["department"],
        "Humanities and Social Sciences",
    )
    check("HSS alias resolves the same", find_courses("HSS", 400, "elective", "")["match_count"], 4)
    check(
        "Programme Core at 400 level is excluded",
        find_courses("Humanities", 400, "", "")["match_count"],
        5,
    )

    print("\nQ19 Mathematics Open Electives")
    maths = find_courses("Mathematics", 0, "Open Elective", "")
    check("count", maths["match_count"], 1)
    check("code", [m["course_code"] for m in maths["matches"]], ["MTL3010"])

    print("\nQ17 slot P4 and Q16 clash check")
    check("P4 meetings", get_slot_timing("P4")["meetings"],
          [{"day": "Thursday", "start_time": "14:00", "end_time": "17:00", "slot_type": "laboratory"}])
    check("CSL7620 vs CSL7570 clash", check_slot_clash("CSL7620", "CSL7570")["clash"], False)
    check("CSL7570 vs CSL7580 clash", check_slot_clash("CSL7570", "CSL7580")["clash"], False)
    check("CSL7570 vs CSL3030 clash", check_slot_clash("CSL7570", "CSL3030")["clash"], True)

    print("\nQ15 and Q18 examination schedule")
    major = lookup_exam_schedule("CSL7620", "Major")
    check("CSL7620 Major date", [e["date"] for e in major["exams"]], ["2026-11-20"])
    makeup = lookup_exam_schedule("", "Makeup-Major")
    check("Makeup Major date", [e["date"] for e in makeup["exams"]], ["2026-12-03"])

    print("\nQ14, Q21-Q25 instructors and email drafts")
    check("CSL7570 instructor", lookup_course_instructor("CSL7570")["instructor_email"],
          "arvind.menon@iitj.ac.in")
    check("HSL4110 instructor", lookup_course_instructor("HSL4110")["instructor_email"],
          "suchitra.pillai@iitj.ac.in")
    check("unknown course is reported, not guessed",
          lookup_course_instructor("CSL9999")["found"], False)

    leave = draft_student_email(
        "sick_leave", "CSL7570", "viral fever", "", "", 2, "", "", "", "", "", "", ""
    )
    check("leave draft recipient", leave["to"], "arvind.menon@iitj.ac.in")
    check("leave draft mentions the course", "CSL7570" in leave["subject"], True)
    check("leave draft is not sent", leave["status"], "draft_not_sent")
    check(
        "unfilled fields are reported as placeholders",
        "<ROLL NUMBER>" in leave["placeholders_to_fill"],
        True,
    )

    dated = draft_student_email(
        "sick_leave", "CSL3010", "dengue", "2026-10-26", "2026-10-28", 0,
        "", "", "", "Aditi Sharma", "B24CS1001", "B.Tech. CSE", "b24cs1001@iitj.ac.in",
    )
    check("day count derived from dates", "3 day(s)" in dated["subject"], True)
    check("no placeholders left when all fields given", dated["placeholders_to_fill"], [])

    makeup_draft = draft_student_email(
        "makeup_exam", "CSL7620", "dengue", "", "", 0, "Minor-2", "2026-10-14",
        "", "Aditi Sharma", "B24CS1001", "M.Tech. AI and DS", "b24cs1001@iitj.ac.in",
    )
    check("makeup draft recipient", makeup_draft["to"], "rohit.bhagat@iitj.ac.in")
    check("makeup draft cites Form AC-07", "AC-07" in makeup_draft["body"], True)
    check("makeup draft cites AR-04.4", "AR-04.4" in makeup_draft["body"], True)

    condone = draft_student_email(
        "attendance_condonation", "AIL3010", "hospitalisation", "2026-09-01", "2026-09-20",
        0, "", "", "68%", "Aditi Sharma", "B24CS1001", "B.Tech. AI and DS", "b24cs1001@iitj.ac.in",
    )
    check("condonation recipient", condone["to"], "meenal.joshi@iitj.ac.in")
    check("condonation states the percentage", "68%" in condone["body"], True)
    check("condonation cites AR-02.4", "AR-02.4" in condone["body"], True)
    check("rejects an unknown request type",
          "error" in draft_student_email("resignation", "CSL7570", "", "", "", 0, "", "", "", "", "", "", ""),
          True)

    print("\nEscalation log")
    logged = log_unanswered_question("What are the dining options on campus?", "out_of_scope", "self-test")
    check("logged", logged["logged"], True)
    check("log file exists", config.UNANSWERED_LOG.exists(), True)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {failures}")
        return 1
    print("All deterministic checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
