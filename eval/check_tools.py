"""Self-test of the deterministic layer: CSV tools, email drafting and the log.

Runs without an LLM, so it verifies the ground truth behind the schedule and
email questions in questions.json before any model time is spent.

    python eval/check_tools.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from academic_helpdesk import config  # noqa: E402
from academic_helpdesk.tools import catalogue  # noqa: E402
from academic_helpdesk.tools.contact_tools import lookup_course_instructor  # noqa: E402
from academic_helpdesk.tools.email_tools import draft_student_email  # noqa: E402
from academic_helpdesk.tools.escalation_tools import log_unanswered_question  # noqa: E402
from academic_helpdesk.tools.schedule_tools import (  # noqa: E402
    check_slot_clash,
    find_courses,
    get_slot_timing,
    lookup_course,
)

failures: list[str] = []


def check(label: str, actual, expected) -> None:
    if actual == expected:
        print(f"  ok   {label}: {actual!r}")
    else:
        print(f"  FAIL {label}: got {actual!r}, expected {expected!r}")
        failures.append(label)


def codes(result: dict) -> list[str]:
    return sorted(m["course_code"] for m in result["matches"])


def main() -> int:
    print("Structured data")
    courses = catalogue.courses()
    check("courses loaded", len(courses) > 40, True)
    check("faculty loaded", len(catalogue.instructors()) > 30, True)
    orphans = [r["course_code"] for r in courses if catalogue.instructor_by_id(r["instructor_id"]) is None]
    check("no course points at a missing instructor", orphans, [])
    known_slots = {s["slot_code"] for s in catalogue.slots()}
    bad_slots = sorted({r["slot"] for r in courses if r["slot"] and r["slot"] not in known_slots})
    check("every slot code exists in the timetable", bad_slots, [])
    check(
        "every non-project course has a slot or explicit meeting times",
        [
            r["course_code"]
            for r in courses
            if not r["slot"] and not r["meetings"] and r["course_type"] != "Project"
        ],
        [],
    )

    print("\nQ12 Autonomous Systems")
    auto = lookup_course("Autonomous Systems")["matches"]
    check("match", [m["course_code"] for m in auto], ["IDL4010"])
    check("explicit times", auto[0]["slot_timings"], ["Tue 11:00-11:50", "Thu 11:00-11:50", "Fri 11:00-11:50"])
    check("room", auto[0]["room"], "LHC 106")

    print("\nQ13 / Q15 / Q20 counts")
    hss = find_courses("Humanities", 400, "elective", "")
    check("Humanities 400-level electives", hss["match_count"], 7)
    check("HSS alias resolves the same", find_courses("HSS", 400, "elective", "")["match_count"], 7)
    check(
        "codes",
        codes(hss),
        ["HSL4010", "HSL4020", "HSL4030", "HSL4070", "HSL4110", "HSL4120", "HSL4130"],
    )
    check("CSE 400-level", find_courses("Computer Science", 400, "", "")["match_count"], 9)
    check("Electrical", find_courses("Electrical", 0, "", "")["match_count"], 3)
    check("only the current semester is counted", all(m["semester"] == "Semester I" for m in hss["matches"]), True)

    print("\nQ14 / Q17 / Q18 / Q19 lookups")
    nlu = lookup_course("CSL7570")["matches"][0]
    check("CSL7570 title", nlu["course_title"], "Natural Language Understanding")
    check("CSL7570 slot", nlu["slot"], "F")
    check("CSL7570 instructor", nlu["instructor_name"], "Sidharth Ranjan")
    slot_a = get_slot_timing("A")["meetings"]
    check("slot A days", [m["day"] for m in slot_a], ["Monday", "Tuesday", "Thursday"])
    check("slot A time", {(m["start_time"], m["end_time"]) for m in slot_a}, {("09:00", "09:50")})
    check("slot G course count", len(get_slot_timing("G")["courses_in_slot"]), 8)
    game = lookup_course("Computational Game Theory")["matches"][0]
    check("credits", game["credits"], 3)
    check("room", game["room"], "LHC 204")

    print("\nQ16 slot clashes (including courses with explicit times only)")
    check("HSL4010 vs HSL4070 (same slot F)", check_slot_clash("HSL4010", "HSL4070")["clash"], True)
    check("HSL4010 vs HSL4020 (F vs G)", check_slot_clash("HSL4010", "HSL4020")["clash"], False)
    check("CSL4100 vs CSL4180 (explicit times, disjoint)", check_slot_clash("CSL4100", "CSL4180")["clash"], False)
    check("unknown course is reported", check_slot_clash("HSL4010", "ZZZ9999")["clash"], None)

    print("\nQ21-Q25 instructors and email drafts")
    check("CSL7570", lookup_course_instructor("CSL7570")["instructor_email"], "sranjan@iitj.ac.in")
    check("CSL4100", lookup_course_instructor("CSL4100")["instructor_email"], "romibanerjee@iitj.ac.in")
    check("IDL4010", lookup_course_instructor("IDL4010")["instructor_email"], "anoopj@iitj.ac.in")
    check("HSL4010", lookup_course_instructor("HSL4010")["instructor_email"], "hari@iitj.ac.in")
    check("ECL4010", lookup_course_instructor("ECL4010")["instructor_email"], "srivatsa@iitj.ac.in")
    check("unknown course is reported, not guessed", lookup_course_instructor("CSL9999")["found"], False)

    leave = draft_student_email("sick_leave", "CSL7570", "", "", "", 2, "", "", "", "", "", "", "")
    check("leave draft recipient", leave["to"], "sranjan@iitj.ac.in")
    check("leave draft names the course and days", "CSL7570" in leave["subject"] and "2 day" in leave["subject"], True)
    check("leave draft is not sent", leave["status"], "draft_not_sent")
    check("unfilled fields become placeholders", "<ROLL NUMBER>" in leave["placeholders_to_fill"], True)
    check("draft quotes no rule or form number", any(t in leave["body"] for t in ("AR-0", "AC-0", "Clause")), False)

    dated = draft_student_email(
        "sick_leave", "HSL4010", "fever", "2026-08-03", "2026-08-05", 0, "", "", "",
        "A Student", "B24XX1001", "B.Tech. CSE", "b24xx1001@iitj.ac.in",
    )
    check("day count derived from dates", "3 day(s)" in dated["subject"], True)
    check("dates are formatted", "03 August 2026" in dated["body"] and "05 August 2026" in dated["body"], True)
    check("no placeholders when everything is given", dated["placeholders_to_fill"], [])

    makeup = draft_student_email(
        "makeup_exam", "CSL4100", "illness", "", "", 0, "Major", "2026-11-20", "", "", "", "", ""
    )
    check("makeup recipient", makeup["to"], "romibanerjee@iitj.ac.in")
    check("makeup draft names the exam", "Major" in makeup["body"] and "20 November 2026" in makeup["body"], True)

    condone = draft_student_email(
        "attendance_condonation", "IDL4010", "illness", "", "", 0, "", "", "68%", "", "", "", ""
    )
    check("condonation recipient", condone["to"], "anoopj@iitj.ac.in")
    check("condonation states the percentage", "68%" in condone["body"], True)
    check("rejects an unknown request type", "error" in draft_student_email(
        "resignation", "CSL7570", "", "", "", 0, "", "", "", "", "", "", ""), True)

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
