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


def test_extract_marksheet_structured_facts():
    raw_text = (
        "RESULT-CUM-DETAILED MARKS CARD\n"
        "First Semester - December , 2023\n"
        "Roll No. : 23001001065\n"
        "Name : MOHIT\n"
        "1 EE101C - BASIC ELECTRICAL ENGINEERING 4.00 Sessional - 25\n"
        "Theory - 75\n"
        "22\n"
        "37 C+\n"
        "2 CSE204C - OPERATING SYSTEMS 3.00 Sessional - 25\n"
        "Theory - 75\n"
        "22\n"
        "49 B+\n"
        "RESULT : Passed and has obtained 06.55 SGPA.\n"
        "CGPA RESULT : Passed and has obtained 07.42 CGPA.\n"
    )
    facts = extract_facts([(1, raw_text)], semester=1)
    fact_dict = {attr: val for _, attr, val in facts}
    assert fact_dict["Roll number"] == "23001001065"
    assert fact_dict["Name"] == "Mohit"
    assert fact_dict["SGPA (Semester 1)"] == "6.55"
    assert fact_dict["CGPA (after Semester 1)"] == "7.42"
    assert fact_dict["Basic Electrical Engineering grade"] == "C+"
    assert fact_dict["Operating Systems grade"] == "B+"


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


def test_timetable_facts_extraction():
    from smriti.ingest.facts import extract_facts

    sample_timetable = (
        "DEENBANDHU CHHOTU RAM UNIVERSITY OF SCIENCE & TECHNOLOGY\n"
        "Theory Date Sheet of Bachelor of Technology “C” Scheme\n"
        "Time of Exam: 09:30 AM to 12:30 PM for Morning Session (M)\n"
        "Time of Exam: 02:00 PM to 05:00 PM for Evening Session (E)\n"
        "7th Semester (Main, Re-appear & Improvement)\n"
        "02.12.2026 CSE401C Cloud Architecture & Security 18G4 CSE E\n"
        "02.12.2026 CSE403C Machine Learning 18G5 CSE E\n"
        "04.12.2026 CSE421C Distributed Computing 18G8 CSE E\n"
    )
    facts = extract_facts([(6, sample_timetable)])
    fact_dict = {attr: val for _, attr, val in facts}
    assert "Cloud Architecture & Security exam" in fact_dict
    assert "02.12.2026" in fact_dict["Cloud Architecture & Security exam"]
    assert "CSE403C exam" in fact_dict
    assert "02.12.2026" in fact_dict["CSE403C exam"]
    assert "7th Semester BTech CSE Timetable" in fact_dict

    # Test class timetable
    sample_class_tt = (
        "Deenbandhu Chhotu Ram University of Science and Technology, Murthal\n"
        "Computer Science and Engineering Department\n"
        "Time Table for B. Tech 7th Semester (Section A) (July – Dec 2026)\n"
        "MON PT Lab, CSE-3, CVR-212, SD BIO-L CVR-213 ENT-L CVR-213\n"
        "TUE GC-L CVR-214 KR SDE-L CVR-214 VF-5 SC-L CVR-213 JKB\n"
        "Dr. Neetu Verma (9466054310)\n"
    )
    class_facts = extract_facts([(7, sample_class_tt)])
    cf_dict = {attr: val for _, attr, val in class_facts}
    assert "Dr. Neetu Verma contact" in cf_dict
    assert cf_dict["Dr. Neetu Verma contact"] == "9466054310"
    assert "7th Semester BTech CSE Class Timetable" in cf_dict

