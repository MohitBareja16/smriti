from smriti.ingest.chunker import chunk_pages
from smriti.ingest.classify import classify_document
from smriti.ingest.facts import extract_facts
from smriti.ingest.parsers import parse_text


def test_page_markers_split_pages():
    pages = parse_text("first page\n<!-- page -->\nsecond page")
    assert pages == [(1, "first page"), (2, "second page")]


def test_chunks_keep_page_numbers_and_respect_size():
    long_para = " ".join(["word"] * 400)
    chunks = chunk_pages([(1, "short intro"), (2, long_para)], max_chars=300)
    assert chunks[0] == (1, "short intro")
    assert all(page == 2 for page, _ in chunks[1:])
    assert all(len(text) <= 300 for _, text in chunks)


def test_classify_document_types():
    assert classify_document("exam_timetable", "DBMS exam: 10 Dec") == "timetable"
    assert classify_document("marksheet_sem4", "SGPA: 8.6 CGPA: 8.2") == "marksheet"
    assert classify_document("os_past_papers", "previous year question paper") == "past_paper"


def test_extract_key_value_facts():
    facts = extract_facts([(1, "# Title\n- DBMS exam: 10 December 2026\n**CGPA**: 8.2\nnot a fact line")])
    assert (1, "DBMS exam", "10 December 2026") in facts
    assert (1, "CGPA", "8.2") in facts
    assert len(facts) == 2


def test_demo_ingest_encrypts_and_redacts_personal_docs(demo_app):
    docs = {d["title"]: d for d in demo_app.db.list_documents()}
    marksheet = docs["marksheet_sem4"]
    assert marksheet["sensitive"] and marksheet["vault_file"]
    # the search index never contains the raw Aadhaar number or email
    hits = demo_app.db.search("Aadhaar email grade card", k=10)
    assert hits and all("9999 8888 7777" not in c.text and "@example.edu" not in c.text for c in hits)
    # the encrypted original is not readable as plain text
    blob = (demo_app.settings.vault_dir / marksheet["vault_file"]).read_bytes()
    assert b"Alex Demo" not in blob


def test_duplicate_ingest_is_detected(demo_app):
    from smriti.ingest import ingest_file
    from tests.conftest import DATA

    r = ingest_file(DATA / "alex_demo" / "library" / "os_notes.md", demo_app.db, demo_app.vault)
    assert r.duplicate
