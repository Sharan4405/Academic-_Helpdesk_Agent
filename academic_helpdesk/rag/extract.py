"""Turn the raw institute files in data/raw into the markdown the indexer reads.

    python -m academic_helpdesk.rag.extract

Each source file (PDF, DOCX, DOC, XLSX, TXT, CSV) becomes one markdown document in
data/processed/ with the same YAML front matter the hand-written corpus uses, so
the chunker, store and citation code need no special cases. Page boundaries become
"## Page N" headings, which lets answers cite the page.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from academic_helpdesk import config

# folder -> (category, doc_id prefix, issuing office)
FOLDERS = {
    "course_catalogs": ("curriculum", "CC", "Office of Academic Affairs"),
    "office_orders": ("office_order", "OO", "Office of Academic Affairs"),
    "official": ("directory", "OFF", "IIT Jodhpur"),
    "timetables": ("schedule", "TT", "Office of Academic Affairs"),
}

# Filenames that mark a regulation or rule set rather than a one-off circular.
RULE_HINTS = (
    "regulation",
    "guidelines for institute examination",
    "guidelines for the minor examination",
    "overload",
    "branch",
    "credit revision",
    "specilization and minors",
)

# Personal pay data and individual homepages say nothing a student helpdesk should
# answer from, so they stay out of the index.
SKIP_HINTS = ("salary",)
SKIP_SUFFIXES = {".css", ".js", ".png", ".jpg", ".svg", ".download", ".html", ".htm"}

ROWS_PER_GROUP = 15
FACULTY_CSV = "iitj_faculty.csv"


def _clean(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _pdf(path: Path) -> str:
    from pypdf import PdfReader

    # A pre-extracted twin (same stem, .txt) is preferred: it already carries page
    # markers and may have been produced by OCR for scanned originals.
    twin = path.with_suffix(".txt")
    if twin.exists():
        return _clean(twin.read_text(encoding="utf-8", errors="replace"))

    parts = []
    for number, page in enumerate(PdfReader(str(path)).pages, start=1):
        text = _clean(page.extract_text() or "")
        if text:
            parts.append(f"## Page {number}\n\n{text}")
    return "\n\n".join(parts)


def _docx(path: Path) -> str:
    import docx

    document = docx.Document(str(path))
    out = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        rows = [" | ".join(c.text.strip() for c in row.cells) for row in table.rows]
        out.append("\n".join(rows))
    return _clean("\n\n".join(out))


def _doc(path: Path) -> str:
    antiword = shutil.which("antiword")
    if not antiword:
        raise RuntimeError("legacy .doc needs antiword on PATH")
    result = subprocess.run(
        [antiword, str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "antiword failed")
    return _clean(result.stdout)


def _table_groups(header: list[str], rows: list[list[str]]) -> str:
    """Rows in small groups, each prefixed by the header, so any chunk is self-explanatory."""
    head = " | ".join(header)
    groups = []
    for start in range(0, len(rows), ROWS_PER_GROUP):
        body = "\n".join(" | ".join(r) for r in rows[start : start + ROWS_PER_GROUP])
        groups.append(f"{head}\n{body}")
    return "\n\n".join(groups)


def _xlsx(path: Path) -> str:
    import openpyxl

    workbook = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    sections = []
    for sheet in workbook.worksheets:
        rows = []
        for row in sheet.iter_rows(values_only=True):
            cells = ["" if v is None else str(v).strip() for v in row]
            if any(cells):
                rows.append(cells)
        if not rows:
            continue
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        # Drop columns that are empty throughout.
        keep = [i for i in range(width) if any(r[i] for r in rows)]
        rows = [[r[i] for i in keep] for r in rows]
        sections.append(f"## Sheet: {sheet.title}\n\n{_table_groups(rows[0], rows[1:])}")
    return "\n\n".join(sections)


def _faculty_csv(path: Path) -> str:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    by_dept: dict[str, list[list[str]]] = defaultdict(list)
    for r in rows:
        by_dept[r.get("Department") or "Unspecified"].append(
            [
                r.get("Faculty Name", ""),
                r.get("Email ID", ""),
                r.get("Designation", ""),
                r.get("Faculty Category", ""),
                r.get("Other Email IDs", ""),
            ]
        )
    header = ["Faculty Name", "Email", "Designation", "Category", "Other emails (roles)"]
    return "\n\n".join(
        f"## {dept}\n\n{_table_groups(header, people)}" for dept, people in sorted(by_dept.items())
    )


EXTRACTORS = {
    ".pdf": _pdf,
    ".docx": _docx,
    ".doc": _doc,
    ".xlsx": _xlsx,
    ".txt": lambda p: _clean(p.read_text(encoding="utf-8", errors="replace")),
}


def _title(path: Path) -> str:
    title = re.sub(r"\s*\(\d+\)$", "", path.stem)
    title = re.sub(r"[-_]?\d{15,}", "", title)  # CMS timestamps in filenames
    title = re.sub(r"[_]+", " ", title)
    return re.sub(r"\s+", " ", title).strip(" -.")


def _category(folder: str, name: str) -> str:
    category = FOLDERS[folder][0]
    if folder == "office_orders" and any(h in name.lower() for h in RULE_HINTS):
        return "academic_rules"
    return category


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def collect(raw_dir: Path) -> list[tuple[str, Path]]:
    """(folder, file) pairs worth extracting, with .txt twins of PDFs folded in."""
    files = []
    for folder in FOLDERS:
        base = raw_dir / folder
        for path in sorted(p for p in base.iterdir() if p.is_file()):
            if path.suffix.lower() in SKIP_SUFFIXES or any(h in path.name.lower() for h in SKIP_HINTS):
                continue
            if path.suffix.lower() == ".txt" and path.with_suffix(".pdf").exists():
                continue  # consumed by the PDF extractor
            if path.suffix.lower() in EXTRACTORS:
                files.append((folder, path))
    return files


def write_document(out_dir: Path, doc_id: str, meta: dict, body: str) -> None:
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    (out_dir / f"{doc_id}-{_slug(meta['title'])}.md").write_text(
        f"---\n{front}\n---\n\n# {meta['title']}\n\n{body}\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract data/raw into data/processed")
    parser.add_argument("--min-chars", type=int, default=200, help="skip near-empty extractions")
    args = parser.parse_args()

    raw_dir, out_dir = config.RAW_DIR, config.PROCESSED_DIR
    if not raw_dir.is_dir():
        print(f"No raw data at {raw_dir}", file=sys.stderr)
        return 1
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    counters: dict[str, int] = defaultdict(int)
    kept = skipped = 0

    for folder, path in collect(raw_dir):
        _, prefix, office = FOLDERS[folder]
        try:
            body = EXTRACTORS[path.suffix.lower()](path)
        except Exception as exc:
            print(f"  SKIP {path.name}: {type(exc).__name__}: {exc}")
            skipped += 1
            continue
        if len(body) < args.min_chars:
            print(f"  SKIP {path.name}: only {len(body)} chars of text (scanned image?)")
            skipped += 1
            continue

        counters[prefix] += 1
        doc_id = f"{prefix}-{counters[prefix]:02d}"
        meta = {
            "doc_id": doc_id,
            "title": _title(path),
            "category": _category(folder, path.name),
            "issuing_office": office,
            "source_file": f"{folder}/{path.name}",
        }
        write_document(out_dir, doc_id, meta, body)
        kept += 1
        print(f"  {doc_id}  {meta['category']:<14} {len(body):>7} chars  {path.name}")

    faculty = raw_dir / FACULTY_CSV
    if faculty.exists():
        meta = {
            "doc_id": "DIR-00",
            "title": "IIT Jodhpur faculty directory",
            "category": "directory",
            "issuing_office": "IIT Jodhpur",
            "source_file": FACULTY_CSV,
        }
        write_document(out_dir, "DIR-00", meta, _faculty_csv(faculty))
        kept += 1
        print(f"  DIR-00  directory      faculty directory ({FACULTY_CSV})")

    print(f"\nExtracted {kept} documents into {out_dir} ({skipped} skipped).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
