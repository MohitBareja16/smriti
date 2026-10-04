"""SQLite storage: documents, page-aware chunks (FTS5 full-text index), facts and an audit log.

Embedded and serverless, so the whole project installs with one command on a student laptop.
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

from parag.types import Chunk, Fact

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,              -- 'library' | 'personal'
    doc_type TEXT NOT NULL,          -- notes | book | past_paper | marksheet | certificate | timetable | other
    course TEXT,
    sensitive INTEGER NOT NULL DEFAULT 0,
    vault_file TEXT,                 -- encrypted original (sensitive docs only)
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page INTEGER NOT NULL,
    text TEXT NOT NULL               -- PII-redacted for sensitive docs
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, content='chunks', content_rowid='id',
    tokenize='porter unicode61');
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page INTEGER NOT NULL,
    attribute TEXT NOT NULL,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""

_WORD = re.compile(r"[A-Za-z0-9]+")
STOPWORDS = frozenset({
    "a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "is", "are", "was", "were", "be",
    "been", "my", "me", "i", "you", "your", "what", "which", "who", "whom", "when", "where", "why",
    "how", "does", "do", "did", "from", "with", "by", "as", "at", "it", "its", "this", "that", "these",
    "those", "can", "could", "should", "would", "please", "tell", "give", "show", "about", "explain",
    "describe",
})


def tokens(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def content_tokens(text: str) -> list[str]:
    return [w for w in tokens(text) if w not in STOPWORDS and len(w) > 1]


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    # ---- documents -------------------------------------------------------------------
    def find_by_hash(self, sha256: str) -> int | None:
        row = self.conn.execute("SELECT id FROM documents WHERE sha256 = ?", (sha256,)).fetchone()
        return row["id"] if row else None

    def add_document(self, *, title: str, path: str, sha256: str, kind: str, doc_type: str,
                     course: str | None, sensitive: bool, vault_file: str | None) -> int:
        cur = self.conn.execute(
            "INSERT INTO documents (title, path, sha256, kind, doc_type, course, sensitive, vault_file, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title, path, sha256, kind, doc_type, course, int(sensitive), vault_file, time.time()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_documents(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM documents ORDER BY id").fetchall()

    def get_document(self, doc_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()

    def delete_document(self, doc_id: int) -> None:
        self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self.conn.commit()

    # ---- chunks + search -------------------------------------------------------------
    def add_chunks(self, doc_id: int, pages_and_texts: list[tuple[int, str]]) -> None:
        self.conn.executemany(
            "INSERT INTO chunks (doc_id, page, text) VALUES (?, ?, ?)",
            [(doc_id, page, text) for page, text in pages_and_texts],
        )
        self.conn.commit()

    def search(self, query: str, k: int = 5, *, course: str | None = None, kind: str | None = None,
               doc_title: str | None = None) -> list[Chunk]:
        """BM25 full-text search with optional metadata filters. Terms are OR-ed, ranked by BM25."""
        terms = content_tokens(query)
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in dict.fromkeys(terms))
        sql = (
            "SELECT c.id, c.doc_id, c.page, c.text, d.title, d.course, d.kind, bm25(chunks_fts) AS rank "
            "FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid JOIN documents d ON d.id = c.doc_id "
            "WHERE chunks_fts MATCH ?"
        )
        params: list = [match]
        if course:
            sql += " AND lower(d.course) = lower(?)"
            params.append(course)
        if kind:
            sql += " AND d.kind = ?"
            params.append(kind)
        if doc_title:
            sql += " AND lower(d.title) LIKE lower(?)"
            params.append(f"%{doc_title}%")
        sql += " ORDER BY rank LIMIT ?"
        params.append(k)
        rows = self.conn.execute(sql, params).fetchall()
        return [
            Chunk(id=r["id"], doc_id=r["doc_id"], doc_title=r["title"], page=r["page"], text=r["text"],
                  course=r["course"], kind=r["kind"], score=-float(r["rank"]))
            for r in rows
        ]

    def courses(self) -> list[str]:
        rows = self.conn.execute("SELECT DISTINCT course FROM documents WHERE course IS NOT NULL").fetchall()
        return [r["course"] for r in rows]

    # ---- facts -----------------------------------------------------------------------
    def add_facts(self, doc_id: int, facts: list[tuple[int, str, str]]) -> None:
        self.conn.executemany(
            "INSERT INTO facts (doc_id, page, attribute, value) VALUES (?, ?, ?, ?)",
            [(doc_id, page, attr, value) for page, attr, value in facts],
        )
        self.conn.commit()

    def all_facts(self) -> list[Fact]:
        rows = self.conn.execute(
            "SELECT f.attribute, f.value, f.page, f.doc_id, d.title FROM facts f "
            "JOIN documents d ON d.id = f.doc_id ORDER BY f.id"
        ).fetchall()
        return [Fact(attribute=r["attribute"], value=r["value"], doc_id=r["doc_id"], doc_title=r["title"],
                     page=r["page"]) for r in rows]

    # ---- audit -----------------------------------------------------------------------
    def audit(self, action: str, detail: str) -> None:
        self.conn.execute("INSERT INTO audit (ts, action, detail) VALUES (?, ?, ?)",
                          (time.time(), action, detail))
        self.conn.commit()

    def audit_log(self, limit: int = 50) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
