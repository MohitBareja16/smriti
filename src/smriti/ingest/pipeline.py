"""Ingestion pipeline: parse → classify → PII check → (encrypt) → chunk → index → extract facts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from smriti.graph import KnowledgeGraph
from smriti.guardrails.pii import find_pii, redact
from smriti.ingest.chunker import chunk_with_topics
from smriti.ingest.classify import classify_document
from smriti.ingest.facts import extract_facts
from smriti.ingest.parsers import UnsupportedFileError, parse
from smriti.library import detect_semester
from smriti.storage import Database
from smriti.vault import Vault

PERSONAL_TYPES = {"marksheet", "certificate", "timetable"}
_COURSE_RE = re.compile(r"\b([A-Za-z]{2,5}\d{2,4}[A-Za-z]?)\b")


class EmptyDocumentError(UnsupportedFileError):
    """Raised when a document yields no extractable text chunks."""


@dataclass
class IngestResult:
    doc_id: int
    title: str
    doc_type: str
    kind: str
    sensitive: bool
    chunks: int
    facts: int
    duplicate: bool = False


def ingest_file(path: Path, db: Database, vault: Vault, *, course: str | None = None,
                semester: int | None = None,
                kind: str | None = None) -> IngestResult:
    path = Path(path)
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    title = path.stem
    if (existing := db.find_by_hash(sha)) is not None:
        row = db.get_document(existing)
        return IngestResult(existing, row["title"], row["doc_type"], row["kind"], bool(row["sensitive"]),
                            0, 0, duplicate=True)

    pages = parse(path)
    full_text = "\n".join(t for _, t in pages)
    chunks = chunk_with_topics(pages) if full_text.strip() else []
    if not pages or not full_text.strip() or not chunks:
        raise EmptyDocumentError(
            f"No readable text could be extracted from '{path.name}'. "
            "If this is a scanned/image PDF, ensure Tesseract OCR is installed or upload a text-selectable file."
        )

    explicit_kind = kind
    doc_type = classify_document(title, full_text)
    kind = kind or ("personal" if doc_type in PERSONAL_TYPES else "library")
    sensitive = kind == "personal" or (explicit_kind != "library" and bool(find_pii(full_text)))

    if course is None:
        m_course = _COURSE_RE.search(f"{title}\n{full_text[:400]}")
        if m_course and any(ch.isdigit() for ch in m_course.group(1)):
            course = m_course.group(1).upper()

    vault_file = None
    if sensitive:
        # Original file is stored only encrypted; the search index only sees redacted text.
        vault_file = vault.put(sha[:16], raw)
        pages = [(p, redact(t)) for p, t in pages]
        chunks = chunk_with_topics(pages)

    stored_path = path.name if sensitive else str(path.resolve())  # never keep paths of sensitive files
    detected_sem = semester if semester is not None else detect_semester(str(path))
    if detected_sem is None and full_text:
        detected_sem = detect_semester(full_text[:500])
    doc_id = db.add_document(title=title, path=stored_path, sha256=sha, kind=kind, doc_type=doc_type,
                             course=course, sensitive=sensitive, vault_file=vault_file,
                             semester=detected_sem)
    db.add_chunks(doc_id, chunks)
    facts = extract_facts(pages, semester=detected_sem) if kind == "personal" else []
    db.add_facts(doc_id, facts)
    KnowledgeGraph(db).rebuild()
    db.audit("ingest", f"{title} type={doc_type} kind={kind} sensitive={sensitive} chunks={len(chunks)}")
    return IngestResult(doc_id, title, doc_type, kind, sensitive, len(chunks), len(facts))
