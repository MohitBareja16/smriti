"""SQLite storage: documents, page-aware chunks (FTS5 full-text index), facts and an audit log.

Embedded and serverless, so the whole project installs with one command on a student laptop.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from smriti.storage.embeddings import LocalEmbedder, cosine_from_blob
from smriti.types import Chunk, Fact

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,              -- 'library' | 'personal'
    doc_type TEXT NOT NULL,          -- notes | book | past_paper | marksheet | certificate | timetable | other
    course TEXT,
    semester INTEGER,
    sensitive INTEGER NOT NULL DEFAULT 0,
    vault_file TEXT,                 -- encrypted original (sensitive docs only)
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page INTEGER NOT NULL,
    text TEXT NOT NULL,              -- PII-redacted for sensitive docs
    topic TEXT                       -- nearest heading, e.g. "Deadlock"
);
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    dim INTEGER NOT NULL,
    vec BLOB NOT NULL
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
CREATE TABLE IF NOT EXISTS traces (
    trace_id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    question TEXT NOT NULL,          -- PII-redacted
    path TEXT NOT NULL,
    intent TEXT NOT NULL,
    confidence REAL NOT NULL,
    latency_ms REAL NOT NULL,
    llm_calls INTEGER NOT NULL,
    llm_tokens INTEGER NOT NULL,
    steps TEXT NOT NULL              -- JSON list of {name, detail, ms}, PII-redacted
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}',
    ui_element_json TEXT,
    attachments_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_thread ON chat_messages(thread_id, id);
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
    def __init__(self, path: Path | str, *, embedder: LocalEmbedder | None = None):
        self.path = str(path)
        self._lock = threading.RLock()
        self._embedder = embedder
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.conn.executescript(SCHEMA)
        self._migrate()

    def attach_embedder(self, embedder: LocalEmbedder | None) -> None:
        self._embedder = embedder

    def _migrate(self) -> None:
        """Add columns introduced after a database was created (older ~/.smriti libraries)."""
        with self._lock:
            for table, column, decl in [("documents", "semester", "INTEGER"), ("chunks", "topic", "TEXT")]:
                cols = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
                if column not in cols:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
            self.conn.commit()

    # ---- documents -------------------------------------------------------------------
    def find_by_hash(self, sha256: str) -> int | None:
        with self._lock:
            row = self.conn.execute("SELECT id FROM documents WHERE sha256 = ?", (sha256,)).fetchone()
            return row["id"] if row else None

    def add_document(self, *, title: str, path: str, sha256: str, kind: str, doc_type: str,
                     course: str | None, sensitive: bool, vault_file: str | None,
                     semester: int | None = None) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO documents (title, path, sha256, kind, doc_type, course, semester, sensitive, "
                "vault_file, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (title, path, sha256, kind, doc_type, course, semester, int(sensitive), vault_file, time.time()),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def list_documents(self) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute("SELECT * FROM documents ORDER BY id").fetchall()

    def indexed_paths(self) -> set[str]:
        """Return resolved filesystem paths of currently indexed non-sensitive documents."""
        paths: set[str] = set()
        for d in self.list_documents():
            if d["sensitive"] or not d["path"]:
                continue
            try:
                paths.add(str(Path(d["path"]).expanduser().resolve()))
            except OSError:
                continue
        return paths

    def find_matching_documents(
        self, query: str, *, kind: str | None = None, limit: int = 3
    ) -> list[sqlite3.Row]:
        """Find indexed documents explicitly referenced by title, filename stem, or course code."""
        generic_doc_words = {
            "pdf", "file", "doc", "docs", "document", "documents", "summarize", "summary",
            "uploaded", "indexed", "notes", "note", "book", "books", "lecture", "chapter",
            "paper", "papers", "exam", "syllabus", "timetable", "my", "the", "latest",
        }
        q_low = (query or "").lower()
        q_norm = re.sub(r"[^a-z0-9]+", " ", q_low).strip()
        q_toks = {t for t in content_tokens(query) if t not in generic_doc_words}
        scored: list[tuple[float, sqlite3.Row]] = []
        for d in self.list_documents():
            if kind and d["kind"] != kind:
                continue
            title = (d["title"] or "").strip()
            title_norm = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
            t_toks = {t for t in content_tokens(title_norm) if t not in generic_doc_words}
            course = (d["course"] or "").strip().lower()
            score = 0.0
            if len(title_norm) >= 4 and re.search(rf"(?<![a-z0-9]){re.escape(title_norm)}(?![a-z0-9])", q_norm):
                score = 100.0
            elif course and len(course) >= 4 and re.search(rf"\b{re.escape(course)}\b", q_low):
                score = 88.0
            elif t_toks and q_toks:
                inter = len(t_toks & q_toks)
                if inter >= 1:
                    ratio = inter / len(t_toks)
                    if ratio >= 0.5 or inter >= 2:
                        score = 60.0 + 30.0 * ratio
            if score >= 60.0:
                scored.append((score, d))
        scored.sort(key=lambda pair: (-pair[0], -int(pair[1]["id"])))
        return [d for _, d in scored[:limit]]

    def get_document(self, doc_id: int) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()

    def delete_document(self, doc_id: int) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            self.conn.commit()

    # ---- chunks + hybrid search ------------------------------------------------------
    def add_chunks(self, doc_id: int, chunks: list[tuple]) -> None:
        """chunks: (page, text) or (page, text, topic)."""
        if not chunks:
            return
        with self._lock:
            inserted_ids: list[int] = []
            for c in chunks:
                cur = self.conn.execute(
                    "INSERT INTO chunks (doc_id, page, text, topic) VALUES (?, ?, ?, ?)",
                    (doc_id, c[0], c[1], c[2] if len(c) > 2 else None),
                )
                inserted_ids.append(int(cur.lastrowid))
            self.conn.commit()
        if self._embedder is not None and self._embedder.available:
            vecs = self._embedder.encode_many([c[1] for c in chunks])
            if len(vecs) == len(inserted_ids):
                with self._lock:
                    self.conn.executemany(
                        "INSERT OR REPLACE INTO chunk_embeddings (chunk_id, dim, vec) VALUES (?, ?, ?)",
                        [(cid, dim, blob) for cid, (dim, blob) in zip(inserted_ids, vecs, strict=True)],
                    )
                    self.conn.commit()

    def backfill_embeddings(self, batch_size: int = 64) -> int:
        """Compute missing dense embeddings for existing chunks when hybrid search is enabled."""
        if self._embedder is None or not self._embedder.available:
            return 0
        with self._lock:
            rows = self.conn.execute(
                "SELECT c.id, c.text FROM chunks c LEFT JOIN chunk_embeddings e ON e.chunk_id = c.id "
                "WHERE e.chunk_id IS NULL ORDER BY c.id"
            ).fetchall()
        total = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            vecs = self._embedder.encode_many([r["text"] for r in batch])
            if len(vecs) != len(batch):
                continue
            with self._lock:
                self.conn.executemany(
                    "INSERT OR REPLACE INTO chunk_embeddings (chunk_id, dim, vec) VALUES (?, ?, ?)",
                    [(int(r["id"]), dim, blob) for r, (dim, blob) in zip(batch, vecs, strict=True)],
                )
                self.conn.commit()
            total += len(batch)
        return total

    def _filter_clauses(
        self,
        *,
        course: str | None = None,
        kind: str | None = None,
        doc_title: str | None = None,
        semester: int | None = None,
        topic: str | None = None,
    ) -> tuple[str, list]:
        clauses = []
        params: list = []
        if course:
            clauses.append(" AND lower(d.course) = lower(?)")
            params.append(course)
        if kind:
            clauses.append(" AND d.kind = ?")
            params.append(kind)
        if doc_title:
            clauses.append(" AND lower(d.title) LIKE lower(?)")
            params.append(f"%{doc_title}%")
        if semester is not None:
            clauses.append(" AND d.semester = ?")
            params.append(semester)
        if topic:
            clauses.append(" AND lower(c.topic) LIKE lower(?)")
            params.append(f"%{topic}%")
        return "".join(clauses), params

    def search(self, query: str, k: int = 5, *, course: str | None = None, kind: str | None = None,
               doc_title: str | None = None, semester: int | None = None,
               topic: str | None = None) -> list[Chunk]:
        """Hybrid search (FTS5 BM25 + optional dense vector RRF) with metadata filters."""
        extra_sql, extra_params = self._filter_clauses(
            course=course, kind=kind, doc_title=doc_title, semester=semester, topic=topic
        )
        bm25_chunks: list[Chunk] = []
        terms = content_tokens(query)
        use_hybrid = self._embedder is not None and self._embedder.available
        bm25_limit = max(k * 4, 20) if use_hybrid else k
        if terms:
            match = " OR ".join(f'"{t}"' for t in dict.fromkeys(terms))
            sql = (
                "SELECT c.id, c.doc_id, c.page, c.text, c.topic, d.title, d.course, d.kind, bm25(chunks_fts) AS rank "
                "FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid JOIN documents d ON d.id = c.doc_id "
                f"WHERE chunks_fts MATCH ?{extra_sql} ORDER BY rank LIMIT ?"
            )
            with self._lock:
                rows = self.conn.execute(sql, [match, *extra_params, bm25_limit]).fetchall()
            bm25_chunks = [
                Chunk(id=r["id"], doc_id=r["doc_id"], doc_title=r["title"], page=r["page"], text=r["text"],
                      course=r["course"], kind=r["kind"], score=-float(r["rank"]), topic=r["topic"])
                for r in rows
            ]

        # Also check title/course metadata matches so naming a freshly uploaded filename retrieves its chunks
        title_docs = self.find_matching_documents(query, kind=kind, limit=2) if not doc_title else []
        meta_chunks: list[Chunk] = []
        for d in title_docs:
            if course and (d["course"] or "").lower() != course.lower():
                continue
            if semester is not None and d["semester"] != semester:
                continue
            meta_chunks.extend(self.document_chunks(int(d["id"]))[: max(k, 4)])

        if not use_hybrid and not meta_chunks:
            return bm25_chunks[:k]

        vec_top: list[tuple[float, sqlite3.Row]] = []
        if use_hybrid:
            q_blob = self._embedder.encode_one(query)
            if q_blob is not None:
                vec_sql = (
                    "SELECT c.id, c.doc_id, c.page, c.text, c.topic, d.title, d.course, d.kind, e.vec "
                    "FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id "
                    f"JOIN documents d ON d.id = c.doc_id WHERE 1=1{extra_sql}"
                )
                with self._lock:
                    vec_rows = self.conn.execute(vec_sql, extra_params).fetchall()
                scored_vec: list[tuple[float, sqlite3.Row]] = []
                for r in vec_rows:
                    sim = cosine_from_blob(q_blob, r["vec"])
                    if sim >= 0.20:
                        scored_vec.append((sim, r))
                scored_vec.sort(key=lambda pair: -pair[0])
                vec_top = scored_vec[: max(k * 4, 20)]

        if not vec_top and not bm25_chunks and not meta_chunks:
            return []

        rrf: dict[int, float] = {}
        by_id: dict[int, Chunk] = {}
        for rank, c in enumerate(bm25_chunks, 1):
            rrf[c.id] = rrf.get(c.id, 0.0) + 1.0 / (60 + rank)
            by_id[c.id] = c
        for rank, c in enumerate(meta_chunks, 1):
            rrf[c.id] = rrf.get(c.id, 0.0) + 1.0 / (50 + rank)
            by_id.setdefault(c.id, c)
        for rank, (sim, r) in enumerate(vec_top, 1):
            cid = int(r["id"])
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (60 + rank)
            if cid not in by_id:
                by_id[cid] = Chunk(
                    id=cid, doc_id=r["doc_id"], doc_title=r["title"], page=r["page"], text=r["text"],
                    course=r["course"], kind=r["kind"], score=sim, topic=r["topic"],
                )
        ranked_ids = sorted(by_id, key=lambda cid: -rrf[cid])[:k]
        out: list[Chunk] = []
        for cid in ranked_ids:
            c = by_id[cid]
            out.append(Chunk(
                id=c.id, doc_id=c.doc_id, doc_title=c.doc_title, page=c.page, text=c.text,
                course=c.course, kind=c.kind, score=rrf[cid], topic=c.topic,
            ))
        return out

    def library_tree(self) -> list[sqlite3.Row]:
        """One row per (document, topic) with semester and course, in reading order."""
        with self._lock:
            return self.conn.execute(
                "SELECT d.semester, d.course, d.title, d.kind, d.doc_type, c.topic, MIN(c.page) AS first_page, "
                "COUNT(*) AS chunks, MIN(c.id) AS first_chunk FROM documents d JOIN chunks c ON c.doc_id = d.id "
                "GROUP BY d.id, c.topic ORDER BY d.semester IS NULL, d.semester, d.course IS NULL, d.course, "
                "d.title, first_chunk").fetchall()

    def document_chunks(self, doc_id: int) -> list[Chunk]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT c.id, c.doc_id, c.page, c.text, c.topic, d.title, d.course, d.kind FROM chunks c "
                "JOIN documents d ON d.id = c.doc_id WHERE c.doc_id = ? ORDER BY c.id", (doc_id,)).fetchall()
            return [Chunk(id=r["id"], doc_id=r["doc_id"], doc_title=r["title"], page=r["page"], text=r["text"],
                          course=r["course"], kind=r["kind"], topic=r["topic"]) for r in rows]

    def courses(self) -> list[str]:
        with self._lock:
            rows = self.conn.execute("SELECT DISTINCT course FROM documents WHERE course IS NOT NULL").fetchall()
            return [r["course"] for r in rows]

    # ---- facts -----------------------------------------------------------------------
    def add_facts(self, doc_id: int, facts: list[tuple[int, str, str]]) -> None:
        with self._lock:
            self.conn.executemany(
                "INSERT INTO facts (doc_id, page, attribute, value) VALUES (?, ?, ?, ?)",
                [(doc_id, page, attr, value) for page, attr, value in facts],
            )
            self.conn.commit()

    def all_facts(self) -> list[Fact]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT f.attribute, f.value, f.page, f.doc_id, d.title FROM facts f "
                "JOIN documents d ON d.id = f.doc_id ORDER BY f.id"
            ).fetchall()
            return [Fact(attribute=r["attribute"], value=r["value"], doc_id=r["doc_id"], doc_title=r["title"],
                         page=r["page"]) for r in rows]

    # ---- traces ----------------------------------------------------------------------
    def add_trace(self, row: dict) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO traces (trace_id, ts, question, path, intent, confidence, latency_ms, "
                "llm_calls, llm_tokens, steps) VALUES (:trace_id, :ts, :question, :path, :intent, :confidence, "
                ":latency_ms, :llm_calls, :llm_tokens, :steps)", row)
            self.conn.commit()

    def get_trace(self, trace_id: str) -> sqlite3.Row | None:
        """Exact id, or a unique prefix (like git short hashes)."""
        with self._lock:
            rows = self.conn.execute("SELECT * FROM traces WHERE trace_id LIKE ? ORDER BY ts DESC LIMIT 2",
                                     (f"{trace_id}%",)).fetchall()
            return rows[0] if len(rows) == 1 else None

    def recent_traces(self, limit: int = 20) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute("SELECT * FROM traces ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()

    # ---- audit -----------------------------------------------------------------------
    def audit(self, action: str, detail: str) -> None:
        with self._lock:
            self.conn.execute("INSERT INTO audit (ts, action, detail) VALUES (?, ?, ?)",
                              (time.time(), action, detail))
            self.conn.commit()

    def audit_log(self, limit: int = 50) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    # ---- conversation threads & multi-turn history -----------------------------------
    @staticmethod
    def _default_thread_title(seed: str) -> str:
        clean = re.sub(r"\s+", " ", (seed or "").strip())
        if not clean:
            return "New Chat"
        return clean[:58].rstrip() + ("..." if len(clean) > 58 else "")

    def create_thread(self, title: str = "New Chat", thread_id: str | None = None) -> str:
        tid = thread_id or uuid.uuid4().hex
        now = time.time()
        with self._lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO threads (id, title, summary, created_at, updated_at) VALUES (?, ?, '', ?, ?)",
                (tid, title or "New Chat", now, now),
            )
            self.conn.commit()
        return tid

    def get_thread(self, thread_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()

    def list_threads(self, limit: int = 50) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                "SELECT t.*, COALESCE(m.cnt, 0) AS message_count "
                "FROM threads t "
                "LEFT JOIN (SELECT thread_id, COUNT(*) AS cnt FROM chat_messages GROUP BY thread_id) m "
                "ON m.thread_id = t.id "
                "ORDER BY t.updated_at DESC, t.created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def rename_thread(self, thread_id: str, title: str) -> bool:
        clean = re.sub(r"\s+", " ", (title or "").strip())
        if not clean:
            return False
        with self._lock:
            cur = self.conn.execute(
                "UPDATE threads SET title = ?, updated_at = ? WHERE id = ?",
                (clean[:120], time.time(), thread_id),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def delete_thread(self, thread_id: str) -> bool:
        with self._lock:
            cur = self.conn.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
            self.conn.commit()
            return cur.rowcount > 0

    def add_chat_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        *,
        meta: dict | None = None,
        ui_element: dict | None = None,
        attachments: list[str] | None = None,
    ) -> int:
        now = time.time()
        with self._lock:
            row = self.get_thread(thread_id)
            if row is None:
                init_title = self._default_thread_title(content) if role == "user" else "New Chat"
                self.create_thread(title=init_title, thread_id=thread_id)
            elif role == "user" and row["title"] == "New Chat":
                self.conn.execute(
                    "UPDATE threads SET title = ? WHERE id = ?",
                    (self._default_thread_title(content), thread_id),
                )
            cur = self.conn.execute(
                "INSERT INTO chat_messages (thread_id, role, content, meta_json, ui_element_json, "
                "attachments_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    thread_id,
                    role,
                    content,
                    json.dumps(meta or {}),
                    json.dumps(ui_element) if ui_element is not None else None,
                    json.dumps(attachments or []),
                    now,
                ),
            )
            self.conn.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now, thread_id))
            self.conn.commit()
            return int(cur.lastrowid)

    def thread_messages(self, thread_id: str, limit: int | None = None) -> list[sqlite3.Row]:
        with self._lock:
            if limit is not None:
                rows = self.conn.execute(
                    "SELECT * FROM chat_messages WHERE thread_id = ? ORDER BY id DESC LIMIT ?",
                    (thread_id, limit),
                ).fetchall()
                return list(reversed(rows))
            return self.conn.execute(
                "SELECT * FROM chat_messages WHERE thread_id = ? ORDER BY id ASC",
                (thread_id,),
            ).fetchall()

    def recent_history(
        self,
        thread_id: str,
        *,
        max_turns: int = 6,
        max_chars: int = 6000,
    ) -> list[dict[str, str]]:
        """Return bounded sliding-window conversation turns [{'role', 'content'}] oldest-to-newest."""
        if max_turns <= 0 or max_chars <= 0:
            return []
        rows = self.thread_messages(thread_id, limit=max_turns * 2)
        kept: list[dict[str, str]] = []
        used_chars = 0
        for r in reversed(rows):
            text = (r["content"] or "").strip()
            if not text:
                continue
            # Truncate huge markdown tables from older assistant replies so they don't crowd the window
            if r["role"] == "assistant" and len(text) > 900:
                text = text[:900].rstrip() + " ..."
            if kept and used_chars + len(text) > max_chars:
                break
            kept.append({"role": r["role"], "content": text})
            used_chars += len(text)
        kept.reverse()
        return kept
