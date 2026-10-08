import sqlite3

from smriti.ingest.chunker import chunk_pages, chunk_with_topics
from smriti.library import build_tree, detect_semester, render_tree
from smriti.storage import Database


def test_topics_come_from_headings_and_split_chunks():
    pages = [(1, "# OS Notes\n\nIntro text.\n\n## Deadlock\n\nFour conditions.\n\n## Paging\n\nFrames."),
             (2, "More about paging on the next page.")]
    chunks = chunk_with_topics(pages)
    assert [(p, t) for p, _, t in chunks] == [(1, "OS Notes"), (1, "Deadlock"), (1, "Paging"), (2, "Paging")]
    assert all(len(c) == 2 for c in chunk_pages(pages))  # old interface unchanged


def test_detect_semester_from_paths_and_questions():
    assert detect_semester("notes/sem5/os.pdf") == 5
    assert detect_semester("Semester-05 DBMS") == 5
    assert detect_semester("my sem 4 marks") == 4
    assert detect_semester("seminar notes") is None
    assert detect_semester("system design") is None


def test_semester_and_topic_filters(demo_app):
    db = demo_app.db
    assert db.search("paging", semester=5) and not db.search("paging", semester=3)
    hits = db.search("paging page table", topic="paging")
    assert hits and all("paging" in (c.topic or "").lower() for c in hits)


def test_agent_drops_semester_filter_when_it_finds_nothing(demo_app):
    a = demo_app.orchestrator.handle("Explain paging from my semester 3 notes", mode="agent")
    searches = [s.detail for s in a.trace if s.name == "s2.tool.search"]
    assert "semester=3" in searches[0] and "all documents" in searches[-1]
    assert any(s.name == "s2.replan" for s in a.trace)


def test_library_tree_groups_semester_course_topics(demo_app):
    tree = build_tree(demo_app.db.library_tree())
    assert "Deadlock" in tree[5]["OS"]["os_notes"].topics
    assert "marksheet_sem4" in tree[4][None]
    text = render_tree(tree)
    assert text.index("Semester 4") < text.index("Semester 5") and "· Deadlock" in text


def test_old_database_is_migrated(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE documents (id INTEGER PRIMARY KEY, title TEXT NOT NULL, path TEXT NOT NULL,
            sha256 TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, doc_type TEXT NOT NULL, course TEXT,
            sensitive INTEGER NOT NULL DEFAULT 0, vault_file TEXT, created_at REAL NOT NULL);
        CREATE TABLE chunks (id INTEGER PRIMARY KEY, doc_id INTEGER NOT NULL, page INTEGER NOT NULL,
            text TEXT NOT NULL);
        INSERT INTO documents VALUES (1, 'old', 'old.md', 'abc', 'library', 'notes', 'OS', 0, NULL, 0);
    """)
    con.commit()
    con.close()
    db = Database(path)
    cols = {r["name"] for r in db.conn.execute("PRAGMA table_info(documents)")}
    assert "semester" in cols and db.list_documents()[0]["title"] == "old"
