"""Deterministic lookups over the timetable, course offering list and exam schedule.

Counting and slot questions are answered by code, not by the language model, so
the numbers in an answer cannot drift between runs.
"""

from __future__ import annotations

from academic_helpdesk.tools import catalogue


def lookup_course(course_query: str) -> dict:
    """Look up a course by its code or title, with slot, timings, room and instructor.

    Use this for "what is the slot for X", "who teaches X", "how many credits is X",
    "which room is X in".

    Args:
        course_query: A course code such as "CSL7620" or a title or part of a
            title such as "Autonomous Systems".

    Returns:
        A dict with "matches" (a list of full course records) and "match_count".
    """
    needle = (course_query or "").strip().lower().replace(" ", "")
    if not needle:
        return {"matches": [], "match_count": 0, "note": "Empty query."}

    exact = [r for r in catalogue.courses() if r["course_code"].lower() == needle]
    if exact:
        return {
            "matches": [catalogue.course_view(r) for r in exact],
            "match_count": len(exact),
        }

    words = [w for w in (course_query or "").strip().lower().split() if len(w) > 2]
    matches = [
        r
        for r in catalogue.courses()
        if needle in r["course_code"].lower()
        or (words and all(w in r["course_title"].lower() for w in words))
    ]
    return {
        "matches": [catalogue.course_view(r) for r in matches],
        "match_count": len(matches),
        "note": "" if matches else "No course in the offering list matches this query.",
    }


def find_courses(department: str, level: int, course_type: str, slot: str) -> dict:
    """Filter and COUNT the courses offered this semester. Use this for any "how many" question.

    All four filters are optional and are combined with AND. The result's
    "match_count" is the authoritative count -- report it verbatim and do not
    recount the list yourself.

    Args:
        department: Department name, loose spellings accepted ("Humanities",
            "HSS", "CSE"). Empty string means any department.
        level: Course level as an integer: 100, 200, 300, 400, 500, 700. Pass 0
            for any level.
        course_type: One of "Institute Core", "Programme Core", "Core Bouquet",
            "Programme Elective", "HSS Elective", "Project", or the special value
            "elective" which means any elective (Programme Elective or HSS
            Elective). Empty string means any type.
        slot: A slot code such as "G" or "P4". Empty string means any slot.

    Returns:
        A dict with "match_count", "matches", and "filters_applied" echoing how
        each loose filter value was interpreted.
    """
    dept = catalogue.normalise_department(department) if department else ""
    wanted_type = (course_type or "").strip()
    slot_code = (slot or "").strip().upper()

    # "offered this semester" means the current term only.
    rows = [r for r in catalogue.courses() if r["is_current"] == "True"]
    if dept:
        rows = [r for r in rows if r["department"] == dept]
    if level:
        rows = [r for r in rows if int(r["level"]) == int(level)]
    if wanted_type:
        if wanted_type.lower() in {"elective", "electives"}:
            rows = [r for r in rows if r["course_type"] in catalogue.ELECTIVE_TYPES]
        else:
            rows = [r for r in rows if r["course_type"].lower() == wanted_type.lower()]
    if slot_code:
        rows = [r for r in rows if r["slot"].upper() == slot_code]

    return {
        "match_count": len(rows),
        "matches": [catalogue.course_view(r) for r in rows],
        "filters_applied": {
            "department": dept or "any",
            "level": level or "any",
            "course_type": (
                "any elective (Programme or HSS)"
                if wanted_type.lower() in {"elective", "electives"}
                else (wanted_type or "any")
            ),
            "slot": slot_code or "any",
            "semester": "Semester I 2026-27 (the current semester)",
        },
        "source": "courses.csv (course offering list, Semester I 2026-27)",
    }


def get_slot_timing(slot_code: str) -> dict:
    """Return the days and times of a timetable slot.

    Args:
        slot_code: A slot code such as "A", "G", "P4" or "S".

    Returns:
        A dict with "slot", "meetings" and the courses currently in that slot.
    """
    code = (slot_code or "").strip().upper()
    meetings = [
        {
            "day": s["day"],
            "start_time": s["start_time"],
            "end_time": s["end_time"],
            "slot_type": s["slot_type"],
        }
        for s in catalogue.slots()
        if s["slot_code"] == code
    ]
    if not meetings:
        return {"slot": code, "meetings": [], "note": f"No slot '{code}' in the timetable."}

    return {
        "slot": code,
        "meetings": meetings,
        "course_count": sum(1 for r in catalogue.courses() if r["slot"].upper() == code and r["is_current"] == "True"),
        "courses_in_slot": [
            {"course_code": r["course_code"], "course_title": r["course_title"]}
            for r in catalogue.courses()
            if r["slot"].upper() == code and r["is_current"] == "True"
        ],
        "source": "timetable.csv (slot system)",
    }


def lookup_exam_schedule(course_query: str, exam_type: str) -> dict:
    """Look up the date, time and venue of Minor-1, Minor-2, Major or Makeup examinations.

    Args:
        course_query: A course code or title. Empty string returns the whole
            published schedule extract.
        exam_type: "Minor-1", "Minor-2", "Major" or "Makeup-Major". Empty string
            means all examination types.

    Returns:
        A dict with "exams" and "match_count".
    """
    needle = (course_query or "").strip().lower()
    wanted = (exam_type or "").strip().lower()

    rows = catalogue.exams()
    if needle:
        rows = [
            r
            for r in rows
            if needle in r["course_code"].lower()
            or needle in r["course_title"].lower()
            or r["course_code"] == "ALL"
        ]
    if wanted:
        rows = [r for r in rows if r["exam_type"].lower() == wanted]

    return {
        "match_count": len(rows),
        "exams": rows,
        "source": "exam schedule table",
        "note": "" if rows else "No exam table is loaded; exam dates are in the academic calendar documents -- use search_academic_documents.",
    }


def check_slot_clash(course_code_a: str, course_code_b: str) -> dict:
    """Check whether two courses can be registered together, i.e. whether their slots clash.

    Args:
        course_code_a: First course code, for example "CSL7620".
        course_code_b: Second course code, for example "CSL7570".

    Returns:
        A dict with "clash" (bool) and the slot of each course.
    """
    def _find(code: str) -> dict[str, str] | None:
        cleaned = (code or "").strip().lower().replace(" ", "")
        return next(
            (r for r in catalogue.courses() if r["course_code"].lower() == cleaned), None
        )

    row_a, row_b = _find(course_code_a), _find(course_code_b)
    missing = [c for c, r in ((course_code_a, row_a), (course_code_b, row_b)) if r is None]
    if missing:
        return {"clash": None, "note": f"Course not found in the offering list: {missing}"}

    times_a, times_b = catalogue.meeting_intervals(row_a), catalogue.meeting_intervals(row_b)
    if not times_a or not times_b:
        return {"clash": None, "note": "A course has no slot or meeting times on record."}
    overlaps = sorted(
        (day, max(s1, s2), min(e1, e2))
        for day, s1, e1 in times_a
        for day2, s2, e2 in times_b
        if day == day2 and max(s1, s2) < min(e1, e2)
    )
    clash = bool(overlaps)
    return {
        "clash": clash,
        "course_a": {"course_code": row_a["course_code"], "slot": row_a["slot"] or "(explicit times)"},
        "course_b": {"course_code": row_b["course_code"], "slot": row_b["slot"] or "(explicit times)"},
        "overlapping_day_times": [
            f"{day.title()} {s // 60:02d}:{s % 60:02d}-{e // 60:02d}:{e % 60:02d}"
            for day, s, e in overlaps
        ],
        "rule": "Two courses in the same slot cannot be registered together.",
    }
