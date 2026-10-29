"""Header-aware chunking of the markdown corpus.

Each document carries a YAML front-matter block. We parse it once and stamp every
chunk with it, so a retrieved chunk can always be cited as "doc_id -- title"
without a second lookup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from academic_helpdesk import config

FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SECTION_RE = re.compile(r"^(#{2,3})\s+(.*)$", re.MULTILINE)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    metadata: dict = field(default_factory=dict)


def _parse_front_matter(raw: str) -> tuple[dict, str]:
    match = FRONT_MATTER_RE.match(raw)
    if not match:
        return {}, raw
    meta = yaml.safe_load(match.group(1)) or {}
    return meta, raw[match.end():]


def _split_sections(body: str) -> list[tuple[str, str]]:
    """Return (heading, section_text) pairs, keeping any preamble under '(preamble)'."""
    matches = list(SECTION_RE.finditer(body))
    if not matches:
        return [("(document)", body.strip())]

    sections: list[tuple[str, str]] = []
    preamble = body[: matches[0].start()].strip()
    if preamble:
        sections.append(("(preamble)", preamble))

    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        heading = match.group(2).strip()
        text = body[match.end():end].strip()
        if text:
            sections.append((heading, text))
    return sections


def _pack(section_text: str) -> list[str]:
    """Split an over-long section on paragraph boundaries with a small overlap."""
    if len(section_text) <= config.CHUNK_TARGET_CHARS:
        return [section_text]

    paragraphs = [p for p in re.split(r"\n\s*\n", section_text) if p.strip()]
    pieces: list[str] = []
    current = ""
    for para in paragraphs:
        if current and len(current) + len(para) + 2 > config.CHUNK_TARGET_CHARS:
            pieces.append(current.strip())
            current = current[-config.CHUNK_OVERLAP_CHARS:] + "\n\n" + para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current.strip():
        pieces.append(current.strip())
    return pieces


def chunk_document(path: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    meta, body = _parse_front_matter(raw)

    doc_id = str(meta.get("doc_id") or path.stem)
    title = str(meta.get("title") or path.stem)
    category = str(meta.get("category") or "uncategorised")
    issuing_office = str(meta.get("issuing_office") or "")
    order_no = str(meta.get("order_no") or meta.get("notice_no") or "")

    chunks: list[Chunk] = []
    for section_index, (heading, section_text) in enumerate(_split_sections(body)):
        for part_index, piece in enumerate(_pack(section_text)):
            # The header line is embedded with the body so that a query mentioning
            # the document or the section lands on the right chunk.
            header = f"[{doc_id}] {title}"
            if heading not in {"(document)", "(preamble)"}:
                header += f" > {heading}"
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:{section_index}:{part_index}",
                    text=f"{header}\n\n{piece}",
                    metadata={
                        "doc_id": doc_id,
                        "title": title,
                        "category": category,
                        "section": heading,
                        "issuing_office": issuing_office,
                        "order_no": order_no,
                        "source_file": path.name,
                    },
                )
            )
    return chunks


def chunk_corpus(documents_dir: Path | None = None) -> list[Chunk]:
    documents_dir = documents_dir or config.DOCUMENTS_DIR
    chunks: list[Chunk] = []
    for path in sorted(documents_dir.glob("*.md")):
        chunks.extend(chunk_document(path))
    return chunks
