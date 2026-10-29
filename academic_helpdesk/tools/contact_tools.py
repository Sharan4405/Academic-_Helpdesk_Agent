"""Instructor and office contact lookups."""

from __future__ import annotations

from academic_helpdesk.tools import catalogue

OFFICE_CONTACTS = {
    "academic section": "academic.section@iitj.ac.in",
    "examinations unit": "exams@iitj.ac.in",
    "timetable unit": "timetable@iitj.ac.in",
    "dean academic affairs": "doaa@iitj.ac.in",
    "dean student affairs": "dosa@iitj.ac.in",
    "institute medical centre": "medical.officer@iitj.ac.in",
    "accounts section": "fees@iitj.ac.in",
    "ais helpdesk": "ais.support@iitj.ac.in",
}


def lookup_course_instructor(course_code: str) -> dict:
    """Get the instructor's name, email and office for a course. Call this before drafting an email.

    Args:
        course_code: The course code, for example "CSL7570". A course title also
            works if the code is not known.

    Returns:
        A dict with the instructor's details, the course details, and
        "found" (bool).
    """
    cleaned = (course_code or "").strip().lower().replace(" ", "")
    row = next((r for r in catalogue.courses() if r["course_code"].lower() == cleaned), None)

    if row is None:
        words = [w for w in (course_code or "").lower().split() if len(w) > 2]
        row = next(
            (
                r
                for r in catalogue.courses()
                if words and all(w in r["course_title"].lower() for w in words)
            ),
            None,
        )

    if row is None:
        return {
            "found": False,
            "note": (
                f"'{course_code}' is not in the Semester I 2026-27 offering list. "
                "Do not guess an email address."
            ),
        }

    instructor = catalogue.instructor_by_id(row["instructor_id"]) or {}
    return {
        "found": True,
        "course_code": row["course_code"],
        "course_title": row["course_title"],
        "instructor_name": instructor.get("name", ""),
        "instructor_email": instructor.get("email", ""),
        "designation": instructor.get("designation", ""),
        "department": instructor.get("department", ""),
        "office": instructor.get("office", ""),
        "phone_extension": instructor.get("phone_extension", ""),
        "source": "faculty.csv -- faculty directory",
    }


def lookup_faculty_contact(name_or_department: str) -> dict:
    """Look up faculty contact details by name, or list the faculty of a department.

    Args:
        name_or_department: A faculty name ("Suchitra Pillai") or a department
            name ("Humanities", "CSE").

    Returns:
        A dict with "matches" and "match_count".
    """
    needle = (name_or_department or "").strip().lower()
    if not needle:
        return {"matches": [], "match_count": 0, "note": "Empty query."}

    matches = [r for r in catalogue.instructors() if needle in r["name"].lower()]
    if not matches:
        dept = catalogue.normalise_department(name_or_department)
        matches = [r for r in catalogue.instructors() if r["department"] == dept]

    return {
        "match_count": len(matches),
        "matches": matches,
        "source": "faculty.csv -- faculty directory",
        "note": "" if matches else "No such faculty member or department in the directory.",
    }


def lookup_office_contact(office: str) -> dict:
    """Get the email address of an academic administration office.

    Args:
        office: For example "Academic Section", "Examinations Unit",
            "Institute Medical Centre". Empty string lists every office.

    Returns:
        A dict mapping office names to email addresses.
    """
    needle = (office or "").strip().lower()
    if not needle:
        return {"offices": OFFICE_CONTACTS, "source": "office contact list (placeholder addresses)"}

    hits = {k: v for k, v in OFFICE_CONTACTS.items() if needle in k or k in needle}
    return {
        "offices": hits,
        "source": "office contact list (placeholder addresses)",
        "note": "" if hits else "Office not in the contact list.",
    }
