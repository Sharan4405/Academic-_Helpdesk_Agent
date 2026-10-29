"""CSV loading and normalisation for the structured academic data."""

from __future__ import annotations

import csv
from functools import lru_cache

from academic_helpdesk import config

HSS = "School of Liberal Arts (Humanities and Social Sciences)"
AIDS = "School of Artificial Intelligence and Data Science"

DEPARTMENT_ALIASES = {
    "cse": "Computer Science and Engineering",
    "cs": "Computer Science and Engineering",
    "computer science": "Computer Science and Engineering",
    "ai": AIDS,
    "aids": AIDS,
    "ai and ds": AIDS,
    "artificial intelligence": AIDS,
    "ee": "Electrical Engineering",
    "electrical": "Electrical Engineering",
    "hss": HSS,
    "humanities": HSS,
    "humanities department": HSS,
    "humanities and social sciences": HSS,
    "social sciences": HSS,
    "liberal arts": HSS,
    "sla": HSS,
    "economics": "Economics",
    "management": "School of Management and Entrepreneurship",
    "som": "School of Management and Entrepreneurship",
}

# courses.csv stores a machine category; the tools and prompts use these labels.
COURSE_TYPE_LABELS = {
    "elective": "Programme Elective",
    "hss_elective": "HSS Elective",
    "programme_core": "Programme Core",
    "core_bouquet": "Core Bouquet",
    "institute_core": "Institute Core",
    "project": "Project",
}
ELECTIVE_TYPES = {"Programme Elective", "Open Elective", "HSS Elective"}

CURRENT_TERM = "2026-27-I"


def _read(filename: str) -> list[dict[str, str]]:
    path = config.STRUCTURED_DIR / filename
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]


@lru_cache(maxsize=1)
def courses() -> list[dict[str, str]]:
    """courses.csv, with the columns renamed to what the tools use."""
    out = []
    for r in _read("courses.csv"):
        year, _, term = r["semester"].rpartition("-")  # "2026-27-I" -> "2026-27", "I"
        out.append(
            {
                "course_code": r["code"],
                "course_title": r["title"],
                "department": r["department"],
                "level": r["level"],
                "credits": r["credits"],
                "ltp": r["ltp"],
                "course_type": COURSE_TYPE_LABELS.get(r["category"], r["category"]),
                "slot": r["slot"],
                "lab_slot": r.get("lab_slot", ""),
                "meetings": r.get("meetings", ""),
                "room": r["room"],
                "instructor_id": r["instructor_id"],
                "semester": f"Semester {term}",
                "academic_year": year,
                "is_current": str(r["semester"] == CURRENT_TERM),
                "offered_to": r["offered_to"],
                "prerequisites": "",
            }
        )
    return out


@lru_cache(maxsize=1)
def instructors() -> list[dict[str, str]]:
    """faculty.csv (no office or extension columns, so those stay empty)."""
    return [
        {**r, "office": r.get("office", ""), "phone_extension": r.get("phone_extension", "")}
        for r in _read("faculty.csv")
    ]


@lru_cache(maxsize=1)
def slots() -> list[dict[str, str]]:
    return [
        {
            "slot_code": r["slot"],
            "day": r["day"],
            "start_time": r["start"],
            "end_time": r["end"],
            "slot_type": r["type"],
        }
        for r in _read("timetable.csv")
    ]


@lru_cache(maxsize=1)
def exams() -> list[dict[str, str]]:
    """No exam table ships with the structured data; exam dates live in the calendar documents."""
    return _read("exam_schedule.csv")


def instructor_by_id(instructor_id: str) -> dict[str, str] | None:
    return next((r for r in instructors() if r["instructor_id"] == instructor_id), None)


def normalise_department(name: str) -> str:
    """Map a loose department name ('Humanities', 'CSE') to the canonical CSV value."""
    cleaned = name.strip().lower().removesuffix(" department").removeprefix("department of ")
    if not cleaned:
        return ""
    if cleaned in DEPARTMENT_ALIASES:
        return DEPARTMENT_ALIASES[cleaned]
    for row in courses():
        if row["department"].lower() == cleaned:
            return row["department"]
    for alias, canonical in DEPARTMENT_ALIASES.items():
        if alias in cleaned or cleaned in alias:
            return canonical
    for row in courses():
        if cleaned in row["department"].lower():
            return row["department"]
    return name.strip()


def course_view(row: dict[str, str]) -> dict[str, object]:
    """Flatten a course row with its instructor and meeting times resolved."""
    instructor = instructor_by_id(row["instructor_id"]) or {}
    if row["slot"]:
        timings = [
            f"{s['day']} {s['start_time']}-{s['end_time']}"
            for s in slots()
            if s["slot_code"] == row["slot"]
        ]
    else:  # a few courses list explicit meeting times instead of a slot code
        timings = [m.strip() for m in row["meetings"].split(";") if m.strip()]
    return {
        "course_code": row["course_code"],
        "course_title": row["course_title"],
        "department": row["department"],
        "level": int(row["level"]),
        "credits": int(row["credits"]),
        "ltp": row["ltp"],
        "course_type": row["course_type"],
        "slot": row["slot"] or "(no slot code; see meeting times)",
        "lab_slot": row["lab_slot"],
        "slot_timings": timings,
        "room": row["room"],
        "instructor_name": instructor.get("name", ""),
        "instructor_email": instructor.get("email", ""),
        "semester": row["semester"],
        "academic_year": row["academic_year"],
        "offered_to": row["offered_to"],
        "prerequisites": row["prerequisites"],
        "source": "courses.csv (course offering list)",
    }
