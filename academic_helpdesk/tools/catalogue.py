"""CSV loading and normalisation for the structured academic data."""

from __future__ import annotations

import csv
from functools import lru_cache

from academic_helpdesk import config

DEPARTMENT_ALIASES = {
    "cse": "Computer Science and Engineering",
    "cs": "Computer Science and Engineering",
    "computer science": "Computer Science and Engineering",
    "ai": "Artificial Intelligence and Data Science",
    "aids": "Artificial Intelligence and Data Science",
    "ai and ds": "Artificial Intelligence and Data Science",
    "artificial intelligence": "Artificial Intelligence and Data Science",
    "ee": "Electrical Engineering",
    "electrical": "Electrical Engineering",
    "me": "Mechanical Engineering",
    "mechanical": "Mechanical Engineering",
    "maths": "Mathematics",
    "math": "Mathematics",
    "physics": "Physics",
    "chemistry": "Chemistry",
    "bsbe": "Bioscience and Bioengineering",
    "bioscience": "Bioscience and Bioengineering",
    "hss": "Humanities and Social Sciences",
    "humanities": "Humanities and Social Sciences",
    "humanities department": "Humanities and Social Sciences",
    "social sciences": "Humanities and Social Sciences",
    "civil": "Civil and Infrastructure Engineering",
    "cie": "Civil and Infrastructure Engineering",
}

ELECTIVE_TYPES = {"Programme Elective", "Open Elective"}


def _read(filename: str) -> list[dict[str, str]]:
    path = config.STRUCTURED_DIR / filename
    with path.open(encoding="utf-8", newline="") as handle:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]


@lru_cache(maxsize=1)
def courses() -> list[dict[str, str]]:
    return _read("courses.csv")


@lru_cache(maxsize=1)
def instructors() -> list[dict[str, str]]:
    return _read("instructors.csv")


@lru_cache(maxsize=1)
def slots() -> list[dict[str, str]]:
    return _read("slots.csv")


@lru_cache(maxsize=1)
def exams() -> list[dict[str, str]]:
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
    """Flatten a course row with its instructor and slot timings resolved."""
    instructor = instructor_by_id(row["instructor_id"]) or {}
    timings = [
        f"{s['day']} {s['start_time']}-{s['end_time']}"
        for s in slots()
        if s["slot_code"] == row["slot"]
    ]
    return {
        "course_code": row["course_code"],
        "course_title": row["course_title"],
        "department": row["department"],
        "level": int(row["level"]),
        "credits": int(row["credits"]),
        "ltp": row["ltp"],
        "course_type": row["course_type"],
        "slot": row["slot"],
        "slot_timings": timings,
        "room": row["room"],
        "instructor_name": instructor.get("name", ""),
        "instructor_email": instructor.get("email", ""),
        "semester": row["semester"],
        "academic_year": row["academic_year"],
        "offered_to": row["offered_to"],
        "prerequisites": row["prerequisites"],
        "source": "courses.csv (Course Offering List, Semester I 2026-27)",
    }
