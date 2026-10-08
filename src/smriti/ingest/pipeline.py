"""Ingestion pipeline: parse → classify → PII check → (encrypt) → chunk → index → extract facts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from smriti.guardrails.pii import find_pii, redact
from smriti.ingest.chunker import chunk_with_topics
from smriti.ingest.classify import classify_document
from smriti.ingest.facts import extract_facts
from smriti.ingest.parsers import parse
from smriti.library import detect_semester
from smriti.storage import Database
from smriti.vault import Vault

PERSONAL_TYPES = {"marksheet", "certificate", "timetable"}


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
    doc_type = classify_document(title, full_text)
    kind = kind or ("personal" if doc_type in PERSONAL_TYPES else "library")
    sensitive = kind == "personal" or bool(find_pii(full_text))

    vault_file = None
    if sensitive:
        # Original file is stored only encrypted; the search index only sees redacted text.
        vault_file = vault.put(sha[:16], raw)
        pages = [(p, redact(t)) for p, t in pages]

    stored_path = path.name if sensitive else str(path.resolve())  # never keep paths of sensitive files
    doc_id = db.add_document(title=title, path=stored_path, sha256=sha, kind=kind, doc_type=doc_type,
                             course=course, sensitive=sensitive, vault_file=vault_file,
                             semester=semester if semester is not None else detect_semester(str(path)))
    chunks = chunk_with_topics(pages)
    db.add_chunks(doc_id, chunks)
    facts = extract_facts(pages) if kind == "personal" else []
    db.add_facts(doc_id, facts)
    db.audit("ingest", f"{title} type={doc_type} kind={kind} sensitive={sensitive} chunks={len(chunks)}")
    return IngestResult(doc_id, title, doc_type, kind, sensitive, len(chunks), len(facts))
