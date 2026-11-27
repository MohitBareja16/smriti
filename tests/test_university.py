from __future__ import annotations

from pathlib import Path

from smriti.app import build_app
from smriti.config import Settings
from smriti.guardrails.pii import redact_credentials
from smriti.university import (
    AttendanceEntry,
    AttendanceReport,
    SamarthClient,
    SubjectAttendance,
    TimetableReport,
    build_timetable_report,
    clear_samarth_credentials,
    compute_bunk_or_need,
    format_attendance_html,
    format_attendance_markdown,
    format_timetable_html,
    format_timetable_markdown,
    load_samarth_credentials,
    parse_a10dance_html,
    parse_samarth_attendance_detail,
    parse_samarth_attendance_index,
    parse_samarth_timetable,
    save_samarth_credentials,
)
from smriti.university.samarth import _extract_csrf_token, _has_active_captcha
from smriti.vault import Vault

MHT_PATH = Path(__file__).resolve().parent.parent / "DCRUST Attendance Checker.mht"


def test_bunk_or_need_matches_a10dance_math():
    assert compute_bunk_or_need(32, 38) == "Safe to bunk 4 classes"
    assert compute_bunk_or_need(24, 34) == "Attend next 6 classes for 75%"
    assert compute_bunk_or_need(37, 39) == "Safe to bunk 10 classes"
    assert compute_bunk_or_need(39, 40) == "Safe to bunk 12 classes"
    assert compute_bunk_or_need(9, 15) == "Attend next 9 classes for 75%"
    assert compute_bunk_or_need(27, 31) == "Safe to bunk 5 classes"
    assert compute_bunk_or_need(3, 4) == "On 75% border — attend next class"


def test_parse_real_dcrust_mht_and_render_formats():
    raw = MHT_PATH.read_text(encoding="utf-8", errors="ignore")
    report = parse_a10dance_html(raw, roll_number="22001001001")
    assert report.semester_label == "Odd Sem 2026"
    assert len(report.subjects) == 6

    bt = report.subjects[0]
    assert bt.section_code == "BSC-07-A-L"
    assert bt.course_code == "BT221C"
    assert bt.course_name == "BIOLOGY FOR ENGINEERS"
    assert (bt.attended, bt.total) == (32, 38)
    assert bt.percentage_str == "84.21%"
    assert bt.prediction == "Safe to bunk 4 classes"
    assert bt.last_marked == "2026-11-18"
    assert len(bt.entries) == 38

    pts = report.subjects[4]
    assert pts.course_code == "CSE481C"
    assert pts.status_level == "danger"
    assert pts.prediction == "Attend next 9 classes for 75%"

    md = format_attendance_markdown(report)
    assert "Odd Sem 2026" in md
    assert "| Status | Subject | Code |" in md
    assert "BT221C : BIOLOGY FOR ENGINEERS" in md
    assert "Safe to bunk 4 classes" in md
    assert "Attend next 6 classes for 75%" in md

    html = format_attendance_html(report)
    assert "Odd Sem 2026" in html
    assert "BT221C : BIOLOGY FOR ENGINEERS" in html
    assert "Attend next 9 classes for 75%" in html


def test_samarth_csrf_and_captcha_detection():
    commented_html = """
    <form id="login-form" action="/index.php/site/login" method="post">
    <input type="hidden" name="_csrf" value="abc123token">
    <!-- <input id="loginform-verifycode" name="LoginForm[verifyCode]"> -->
    </form>
    """
    assert _extract_csrf_token(commented_html) == "abc123token"
    assert not _has_active_captcha(commented_html)

    active_captcha_html = """
    <form id="login-form" action="/index.php/site/login" method="post">
    <input type="hidden" name="_csrf" value="abc123token">
    <input id="loginform-verifycode" name="LoginForm[verifyCode]">
    </form>
    """
    assert _has_active_captcha(active_captcha_html)


def test_parse_samarth_index_detail_and_timetable():
    index_html = """
    <html><body>
      <h2>Odd Sem 2026</h2>
      <table class="table table-bordered">
        <thead>
          <tr><th>Course Code</th><th>Course Name</th><th>Batch</th><th>Present</th><th>Total</th><th>Action</th></tr>
        </thead>
        <tbody>
          <tr>
            <td>BT221C</td>
            <td>BIOLOGY FOR ENGINEERS</td>
            <td>BSC-07-A-L</td>
            <td>32</td>
            <td>38</td>
            <td><a href="/index.php/student-attendance/attendance/view?id=101">View</a></td>
          </tr>
          <tr>
            <td>CSE405C</td>
            <td>SOFTWARE DESIGN AND ENTERPRISE COMPUTING</td>
            <td>CSE405C-07-A-L</td>
            <td>24</td>
            <td>34</td>
            <td><a href="/index.php/student-attendance/attendance/view?id=102">View</a></td>
          </tr>
        </tbody>
      </table>
    </body></html>
    """
    sem, _, rows = parse_samarth_attendance_index(index_html)
    assert sem == "Odd Sem 2026"
    assert len(rows) == 2
    assert rows[0][0].course_code == "BT221C"
    assert (rows[0][0].attended, rows[0][0].total) == (32, 38)
    assert rows[0][1] == "/index.php/student-attendance/attendance/view?id=101"

    detail_html = """
    <table>
      <tr><th>Date</th><th>Slot</th><th>Status</th></tr>
      <tr><td>18-11-2026</td><td>14:00 - 15:00</td><td>Present</td></tr>
      <tr><td>17-11-2026</td><td>15:00 - 16:00</td><td>Absent</td></tr>
    </table>
    """
    entries, att, tot = parse_samarth_attendance_detail(detail_html)
    assert (att, tot) == (1, 2)
    assert entries[0] == AttendanceEntry(date="2026-11-18", time_slot="14:00 - 15:00", status="PRESENT")
    assert entries[1] == AttendanceEntry(date="2026-11-17", time_slot="15:00 - 16:00", status="ABSENT")

    tt_html = """
    <table>
      <tr><td>Thursday</td><td>10:00 - 11:00</td><td>CSE405C : SOFTWARE DESIGN</td></tr>
    </table>
    """
    sched = parse_samarth_timetable(tt_html, weekday="Thursday")
    assert sched == {"CSE405C": "10:00 - 11:00"}


def test_samarth_multi_semester_filtering_and_detail_summary():
    """Matches live Samarth HTML: thead without <tr>, multiple semesters, and detail-view summary."""
    multi_sem_html = """
    <html><body>
      <table class="table table-bordered table-striped">
        <thead class="border-top">
          <th>S.No</th>
          <th>Class Name</th>
          <th>Course Name</th>
          <th>Academic Term/Term Type</th>
          <th>Academic Year</th>
          <th>View Attendance</th>
        </thead>
        <tr class="text-center">
          <td>1</td>
          <td>CSE302C-06-A-L</td>
          <td>CSE302C : COMPILER DESIGN</td>
          <td>SEMESTER - 6</td>
          <td>2025-2026</td>
          <td><a href="/index.php/student-attendance/attendance/view-attendance?class_id=old">View</a></td>
        </tr>
        <tr class="text-center">
          <td>2</td>
          <td>BSC-07-A-L</td>
          <td>BT221C : BIOLOGY FOR ENGINEERS</td>
          <td>SEMESTER - 7</td>
          <td>2026-2027</td>
          <td><a href="/index.php/student-attendance/attendance/view-attendance?class_id=cur1">View</a></td>
        </tr>
      </table>
    </body></html>
    """
    sem, _, rows = parse_samarth_attendance_index(multi_sem_html, current_only=True)
    assert sem == "Semester 7 (2026-2027)"
    assert len(rows) == 1
    assert rows[0][0].course_code == "BT221C"
    assert rows[0][0].section_code == "BSC-07-A-L"

    detail_html = """
    <table id="w0" class="table table-striped table-bordered detail-view">
      <tr><th>Class Name</th><td>BSC-07-A-L</td></tr>
      <tr><th>Attendance Summary</th><td>Total Classes Taken: 38, Present Count: 32, Absent Count: 6, Leave Count: 0</td></tr>
    </table>
    <table class="table table-striped table-bordered">
      <thead><tr><th>#</th><th>Attendance Date</th><th>Time</th><th>Attendance Status</th></tr></thead>
      <tbody><tr><td>1</td><td>2026-11-18</td><td>14:00 - 15:00</td><td>PRESENT</td></tr></tbody>
    </table>
    """
    entries, att, tot = parse_samarth_attendance_detail(detail_html)
    assert (att, tot) == (32, 38)
    assert entries == [AttendanceEntry(date="2026-11-18", time_slot="14:00 - 15:00", status="PRESENT")]


def test_vault_samarth_credentials_and_redaction(tmp_path):
    vault = Vault(tmp_path / "vault", "vault-pass")
    save_samarth_credentials(vault, "22001001001", "secretPwd!")
    assert load_samarth_credentials(vault) == ("22001001001", "secretPwd!")
    assert clear_samarth_credentials(vault) is True
    assert load_samarth_credentials(vault) is None

    redacted = redact_credentials("Check attendance roll no 22001001001 password mySecret99")
    assert "mySecret99" not in redacted
    assert "[REDACTED:password]" in redacted


def test_orchestrator_inline_samarth_sync_and_followup_rag(tmp_path):
    class FakeSamarthClient(SamarthClient):
        def fetch_attendance(self, roll_number: str, password: str) -> AttendanceReport:
            assert roll_number == "22001001001"
            assert password == "MySecretPwd"
            return AttendanceReport(
                roll_number=roll_number,
                semester_label="Odd Sem 2026",
                fetched_at="Thu, Nov 26",
                subjects=[
                    SubjectAttendance(
                        section_code="BSC-07-A-L",
                        course_code="BT221C",
                        course_name="BIOLOGY FOR ENGINEERS",
                        attended=32,
                        total=38,
                        last_marked="2026-11-18",
                    ),
                    SubjectAttendance(
                        section_code="CSE405C-07-A-L",
                        course_code="CSE405C",
                        course_name="SOFTWARE DESIGN AND ENTERPRISE COMPUTING",
                        attended=24,
                        total=34,
                        last_marked="2026-11-18",
                    ),
                ],
            )

    app = build_app(Settings(data_dir=tmp_path / "data", passphrase="test-vault-pass", llm_backend="extractive"))
    app.orchestrator.samarth_client = FakeSamarthClient()

    # 1. Inline credentials fetch attendance via System 1 (0 LLM calls) and generate HTML attachment
    ans = app.orchestrator.handle("Check my attendance roll no 22001001001 password MySecretPwd")
    assert ans.path == "S1" and ans.llm_calls == 0
    assert "BT221C : BIOLOGY FOR ENGINEERS" in ans.text
    assert "84.21%" in ans.text
    assert "Safe to bunk 4 classes" in ans.text
    assert "Attend next 6 classes for 75%" in ans.text
    assert ans.attachment and Path(ans.attachment).exists()
    assert ans.ui_element and ans.ui_element["name"] == "DcrustAttendance"
    assert len(ans.ui_element["props"]["subjects"]) == 2

    # Ensure plaintext password is never persisted in traces or audit logs
    trace_row = app.db.get_trace(ans.trace_id)
    assert trace_row is not None
    assert "MySecretPwd" not in trace_row["question"]
    assert all("MySecretPwd" not in row["detail"] for row in app.db.audit_log(10))

    # Credentials were encrypted in Vault for subsequent checks
    assert load_samarth_credentials(app.vault) == ("22001001001", "MySecretPwd")

    # 2. Follow-up subject questions resolve in System 1 from indexed RAG facts (0 LLM calls)
    f1 = app.orchestrator.handle("What is my attendance in BT221C?")
    assert f1.path == "S1" and f1.llm_calls == 0
    assert "84.21%" in f1.text and "Safe to bunk 4 classes" in f1.text

    f2 = app.orchestrator.handle("How many classes needed for 75% in CSE405C?")
    assert f2.path == "S1" and f2.llm_calls == 0
    assert "Attend next 6 classes for 75%" in f2.text


def test_timetable_table_calendar_and_orchestrator(tmp_path):
    raw_events = [
        {"id": "old_sem", "title": "CSE302C-06-A-L", "desc": "CSE302C : COMPILER DESIGN",
         "start": 1769000000, "end": 1769003600, "attendance_status": "PRESENT"},
        {"id": "cur_1", "title": "CSE481C-07-3A", "desc": "CSE481C : PROFESSIONAL TRAINING SEMINAR",
         "start": 1785295800, "end": 1785303000, "attendance_status": "PRESENT"},
        {"id": "cur_1", "title": "CSE481C-07-3A", "desc": "CSE481C : PROFESSIONAL TRAINING SEMINAR",
         "start": 1785900600, "end": 1785907800, "attendance_status": "PRESENT"},
        {"id": "cur_1", "title": "CSE481C-07-3A", "desc": "CSE481C : PROFESSIONAL TRAINING SEMINAR",
         "start": 1786505400, "end": 1786512600, "attendance_status": "ABSENT"},
        {"id": "cur_2", "title": "BSC-07-A-L", "desc": "BT221C : BIOLOGY FOR ENGINEERS",
         "start": 1785303000, "end": 1785306600, "attendance_status": ""},
        {"id": "cur_2", "title": "BSC-07-A-L", "desc": "BT221C : BIOLOGY FOR ENGINEERS",
         "start": 1785907800, "end": 1785911400, "attendance_status": "PRESENT"},
        {"id": "cur_2", "title": "BSC-07-A-L", "desc": "BT221C : BIOLOGY FOR ENGINEERS",
         "start": 1786512600, "end": 1786516200, "attendance_status": "PRESENT"},
    ]
    report = build_timetable_report(
        "23001001065", "Semester 7 (2026-2027)", raw_events, current_class_ids={"cur_1", "cur_2"}
    )
    assert len(report.events) == 6
    assert all(e.course_code in {"CSE481C", "BT221C"} for e in report.events)
    assert len(report.weekly_slots) == 2

    md = format_timetable_markdown(report)
    assert "| DAY |" in md and "**MON**" in md and "**SUBJECTS:**" in md
    assert "CSE481C" in md and "BT221C" in md

    html = format_timetable_html(report)
    assert "TABLE" in html and "CALENDAR" in html and "SUBJECTS" in html
    assert "TODAY" in html and "No classes" in html and "Synced from Samarth ERP" in html
    assert "CSE481C" in html and "BT221C" in html

    class FakeTimetableClient(SamarthClient):
        def fetch_timetable(self, roll_number: str, password: str, *, current_only: bool = True) -> TimetableReport:
            return report

    app = build_app(Settings(data_dir=tmp_path / "data", passphrase="test-vault-pass", llm_backend="extractive"))
    app.orchestrator.samarth_client = FakeTimetableClient()

    ans = app.orchestrator.handle("Check my timetable roll no 23001001065 password SecretPass")
    assert ans.path == "S1" and ans.llm_calls == 0
    assert "| DAY |" in ans.text
    assert ans.attachment and Path(ans.attachment).exists()
    assert ans.ui_element and ans.ui_element["name"] == "DcrustTimetable"
    tt_props = ans.ui_element["props"]
    assert len(tt_props["subjects"]) == 2
    assert tt_props["gridStartHour"] <= 9 and tt_props["gridEndHour"] >= 12
    assert all("startMin" in ev and "endMin" in ev for ev in tt_props["events"])
    assert "SecretPass" not in app.db.get_trace(ans.trace_id)["question"]

    f_sched = app.orchestrator.handle("What is my BT221C class schedule?")
    assert f_sched.path == "S1" and f_sched.llm_calls == 0
    assert "BT221C" in f_sched.text or "BIOLOGY" in f_sched.text or "schedule" in f_sched.text.lower()


def test_pyq_parser_sort_search_and_orchestrator(tmp_path):
    from smriti.university.pyq import (
        DcrustPyqClient,
        PyqEntry,
        parse_direct_pdf_links,
        parse_exam_sessions,
        parse_letter_pqp_rows,
        parse_session_sort,
        search_pyqs,
        sync_dcrust_pyqs,
    )

    index_html = """
    <a href='dcrustpqp2.php?examid=14'>june2024</a>
    <a href='dcrustpqp2.php?examid=15'>dec2024</a>
    <a href='dcrustpqp2.php?examid=4'>July 2018 - Ph.D (Entrance Exam)</a>
    """
    assert parse_exam_sessions(index_html) == [
        ("14", "june2024"),
        ("15", "dec2024"),
        ("4", "July 2018 - Ph.D (Entrance Exam)"),
    ]
    assert parse_session_sort("dec2024")[0] == 202412
    assert parse_session_sort("jan,2023")[0] == 202301

    # Notice unclosed onclick quote like live dcrustedp.in HTML
    letter_html = """
    <table>
      <tr><td>1</td><td><a href='dcrustpqp/dec2024/CSE405C.pdf' onclick='return popitup('dcrustpqp/dec2024/CSE405C.pdf')>CSE405C</a></td><td>SOFTWARE DESIGN AND ENTERPRISE COMPUTING</td>
      <tr><td>2</td><td><a href='dcrustpqp/dec2024/cse302c.pdf' onclick='return popitup('dcrustpqp/dec2024/cse302c.pdf')>cse302c</a></td><td>COMPILER DESIGN</td>
    </table>
    """
    rows = parse_letter_pqp_rows(letter_html, exam_id="15", session_label="dec2024")
    assert len(rows) == 2
    assert rows[0].course_code == "CSE405C"
    assert rows[1].course_code == "CSE302C"

    phd_html = "<a href='dcrustpqp/phdJuly2018/COMPUTER SCIENCE AND ENGINEERING.pdf'>COMPUTER SCIENCE AND ENGINEERING</a>"
    phd_rows = parse_direct_pdf_links(phd_html, exam_id="4", session_label="July 2018 - Ph.D (Entrance Exam)")
    assert len(phd_rows) == 1
    assert "%20" in phd_rows[0].remote_url

    class FakePyqClient(DcrustPyqClient):
        def fetch_catalog(self, *, exam_ids=None, max_workers=6, progress_cb=None):
            return [{"exam_id": "14", "label": "june2024"}, {"exam_id": "13", "label": "dec2023"}], [
                PyqEntry("14", "June 2024", "2024-06_june2024", 202406, "CSE302C", "CSE302C",
                         "COMPILER DESIGN", "dcrustpqp/june2024/CSE302C.pdf",
                         "https://www.dcrustedp.in/dcrustpqp/june2024/CSE302C.pdf"),
                PyqEntry("13", "December 2023", "2023-12_dec2023", 202312, "cse302c", "CSE302C",
                         "COMPILER DESIGN", "dcrustpqp/dec2023/cse302c.pdf",
                         "https://www.dcrustedp.in/dcrustpqp/dec2023/cse302c.pdf"),
                PyqEntry("14", "June 2024", "2024-06_june2024", 202406, "CSE303C", "CSE303C",
                         "DATA BASE MANAGEMENT SYSTEM", "dcrustpqp/june2024/CSE303C.pdf",
                         "https://www.dcrustedp.in/dcrustpqp/june2024/CSE303C.pdf"),
            ]

        def download_pdf(self, url, dest):
            dest.parent.mkdir(parents=True, exist_ok=True)
            payload = b"%PDF-1.4\n%fake\n"
            dest.write_bytes(payload)
            return "downloaded", len(payload)

    pyq_dir = tmp_path / "data" / "pyqs"
    cat = sync_dcrust_pyqs(pyq_dir, download=True, max_workers=2, client=FakePyqClient())
    assert len(cat.entries) == 3
    assert all((pyq_dir / e.local_relpath).exists() for e in cat.entries)
    assert (pyq_dir / "by_subject" / "CSE302C - COMPILER DESIGN").is_dir()
    assert (pyq_dir / "by_session").is_dir()

    # Search by code, subject name, and abbreviation
    r_code = search_pyqs("PYQ for CSE302C", pyq_dir)
    assert r_code.total_papers == 2
    assert r_code.matches[0].entries[0].session_sort == 202406  # newest first

    r_name = search_pyqs("Show previous year papers of Compiler Design", pyq_dir)
    assert r_name.matches and r_name.matches[0].course_code == "CSE302C"

    r_abbr = search_pyqs("DBMS pyq", pyq_dir)
    assert r_abbr.matches and r_abbr.matches[0].course_code == "CSE303C"

    # Orchestrator System 1 integration
    app = build_app(Settings(data_dir=tmp_path / "data", passphrase="test-vault-pass", llm_backend="extractive"))
    ans = app.orchestrator.handle("Show all PYQs for Compiler Design")
    assert ans.path == "S1" and ans.llm_calls == 0
    assert ans.ui_element and ans.ui_element["name"] == "DcrustPyqs"
    assert len(ans.attachments) == 2
    assert "CSE302C" in ans.text

    # Topic-analysis questions on past papers must still route to System 2 exam_prep, NOT PYQ file lookup
    from smriti.orchestrator import _wants_pyq_lookup

    assert not _wants_pyq_lookup("Which OS topics come up most in past papers?", pyq_dir)
    assert not _wants_pyq_lookup("What topics are repeatedly asked in Compiler Design past papers?", pyq_dir)


def test_syllabus_classifier_sort_search_and_orchestrator(tmp_path):
    from smriti.university.syllabus import (
        DcrustSyllabusClient,
        classify_syllabus_item,
        parse_syllabus_api_payload,
        search_syllabus,
        sync_dcrust_syllabus,
    )

    e1 = classify_syllabus_item({
        "text": "BTechCSE_Scheme_Syllabus_1-6_Sept2026",
        "url": "https://www.dcrustm.ac.in/uploads/files/File2026092889982.pdf",
    })
    assert e1.department_id == "cse_it" and e1.degree == "B.Tech"
    assert {"1st", "2nd", "3rd"} <= set(e1.covered_years)

    e2 = classify_syllabus_item({
        "text": "B.Tech_3rd year_ME_ V VI SEM C scheme",
        "url": "https://www.dcrustm.ac.in/wp-content/uploads/2020/10/BTech_3rd-year_ME.docx",
    })
    assert e2.department_id == "mech_aero" and e2.year_id == "3rd" and e2.file_type == "DOCX"

    e3 = classify_syllabus_item({
        "text": "B.Tech-Scheme and SylabusFirst Year 27062018",
        "url": "https://www.dcrustm.ac.in/uploads/files/File2022090820341.pdf",
    })
    assert e3.department_id == "common_1st" and e3.year_id == "1st"

    raw_payload = {
        "success": True,
        "data": [
            {"text": "BTechCSE_Scheme_Syllabus_1-6_Sept2026", "url": "https://www.dcrustm.ac.in/uploads/files/cse16.pdf"},
            {"text": "B.Tech._CSE__3-8_Sem_AC_15_14.08.2020", "url": "https://www.dcrustm.ac.in/uploads/cse38.doc"},
            {"text": "B.Tech-Scheme and SylabusFirst Year 27062018", "url": "https://www.dcrustm.ac.in/uploads/1st.pdf"},
            {"text": "BTech_3rd year_ME_ V VI SEM C scheme", "url": "https://www.dcrustm.ac.in/uploads/me3.docx"},
            {"text": "B.Tech. 4th year ECE (C scheme)", "url": "https://www.dcrustm.ac.in/uploads/ece4.pdf"},
        ],
    }

    class FakeSyllabusClient(DcrustSyllabusClient):
        def fetch_catalog(self):
            return parse_syllabus_api_payload(raw_payload)

        def download_document(self, entry, dest):
            dest.parent.mkdir(parents=True, exist_ok=True)
            data = b"%PDF-1.4\n%fake\n" if dest.suffix == ".pdf" else b"PK\x03\x04fake"
            dest.write_bytes(data)
            return "downloaded", len(data), dest

    syl_dir = tmp_path / "data" / "syllabus"
    cat = sync_dcrust_syllabus(syl_dir, download=True, max_workers=2, client=FakeSyllabusClient())
    assert len(cat.entries) == 5
    assert all((syl_dir / e.local_relpath).exists() for e in cat.entries)
    assert (syl_dir / "by_branch").is_dir() and (syl_dir / "by_year").is_dir()

    r_cse3 = search_syllabus("CSE 3rd year syllabus", syl_dir)
    assert r_cse3.branch_id == "cse_it" and r_cse3.year_id == "3rd"
    assert any("CSE" in m.title for m in r_cse3.matches)

    r_cse1 = search_syllabus("B.Tech 1st year CSE syllabus", syl_dir)
    assert any(m.department_id == "common_1st" for m in r_cse1.matches)

    r_ece4 = search_syllabus("ECE 4th year syllabus", syl_dir)
    assert r_ece4.matches and r_ece4.matches[0].department_id == "ece" and r_ece4.matches[0].year_id == "4th"

    r_me5sem = search_syllabus("Mechanical 5th sem syllabus", syl_dir)
    assert r_me5sem.matches and r_me5sem.matches[0].department_id == "mech_aero" and r_me5sem.matches[0].year_id == "3rd"

    app = build_app(Settings(data_dir=tmp_path / "data", passphrase="test-vault-pass", llm_backend="extractive"))
    ans = app.orchestrator.handle("Give me CSE 3rd year syllabus")
    assert ans.path == "S1" and ans.llm_calls == 0
    assert ans.ui_element and ans.ui_element["name"] == "DcrustSyllabus"
    assert len(ans.attachments) >= 1
    assert "DCRUST University Syllabus" in ans.text


def test_pyq_analyzer_units_frequency_and_routing(tmp_path, monkeypatch):
    from smriti.university import (
        PyqCatalog,
        PyqEntry,
        cluster_pyq_questions,
        parse_dcrust_paper,
        pyq_analyzer,
        save_pyq_catalog,
    )

    # 1. Parser handles OCR unit quirks (dup Unit I, Unit OT) & unnumbered 15-mark blocks
    raw_pages = [
        (1, "No. of Printed Pages : 03\n18G9\nB.Tech. EXAMINATION, 2022\nCSE423C\nGREEN COMPUTING\nNote : Attempt Five questions.\n"),
        (
            2,
            (
                "Unit I\n"
                "List any five good computing habits which help green computing. 15\n\n"
                "Write and explain three milestones in green computing history. 15\n"
                "Unit I\n"
                "(a) Advantages of sustainable computing ? 5\n"
                "(b) Efficient resource allocation strategy. 10\n"
                "Unit OT\n"
                "Optimize airflow around servers and networking equipment. 15\n"
                "Unit IV\n"
                "Explain green mobile battery techniques. 15\n"
            ),
        ),
    ]
    parsed = parse_dcrust_paper(raw_pages, course_code="CSE423C", subject_name="GREEN COMPUTING")
    assert [q.unit for q in parsed] == [1, 1, 2, 3, 4]
    assert "good computing habits" in parsed[0].text.lower() and parsed[0].marks == "15"
    assert "milestones" in parsed[1].text.lower()
    assert "(a)" in parsed[2].text and "(b)" in parsed[2].text

    # 2. Prepare synthetic 3-paper catalog & parsed outputs for orchestrator routing test
    pyq_dir = tmp_path / "data" / "pyqs"
    entries = []
    fake_docs = {}
    for slug, label, sort_val, q1_txt, q2_txt in [
        (
            "2024-06_june2024",
            "June 2024",
            202406,
            "1. Explain the following : 15\n(a) Virtualization\n(b) Green OS\nUnit I\n2. Explain government initiatives towards green computing. 15\n3. What is Compiler Optimization ? Explain Product Longevity. 15\nUnit II\n4. Explain Server Consolidation. 15",
            None,
        ),
        (
            "2024-12_dec2024",
            "December 2024",
            202412,
            "Unit I\nDiscuss green computing and various compiler optimization techniques with examples. 15\nDescribe various industry initiatives in green computing. 15",
            None,
        ),
        (
            "2023-12_dec2023",
            "December 2023",
            202312,
            "Unit I\nExplain how Industry can contribute in Green Computing ? Discuss approaches followed in industry. 15\nDiscuss compiler optimization role in Green Computing. 15",
            None,
        ),
    ]:
        rel = f"by_subject/CSE423C - GREEN COMPUTING/{slug}_CSE423C.pdf"
        p = pyq_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"%PDF-1.4\n%stub\n")
        fake_docs[str(p.resolve())] = [(1, "CSE423C GREEN COMPUTING"), (2, q1_txt)]
        entries.append(
            PyqEntry(
                exam_id=str(sort_val),
                session_label=label,
                session_slug=slug,
                session_sort=sort_val,
                raw_code="CSE423C",
                course_code="CSE423C",
                subject_name="GREEN COMPUTING",
                remote_path=f"{slug}/CSE423C.pdf",
                remote_url=f"https://www.dcrustedp.in/dcrustpqp/{slug}/CSE423C.pdf",
                local_relpath=rel,
                status="downloaded",
                size_bytes=20,
            )
        )

    save_pyq_catalog(
        pyq_dir,
        PyqCatalog(
            source_url="https://www.dcrustedp.in/dcrustpqp.php",
            updated_at="2026-11-27T15:00:00Z",
            exam_sessions=[],
            entries=entries,
        ),
    )
    monkeypatch.setattr(pyq_analyzer, "parse_document", lambda p: fake_docs[str(Path(p).resolve())])

    # Frequency ranking merges paraphrases accurately without collapsing distinct topics on subject name
    clusters = cluster_pyq_questions(
        [
            q
            for e in entries
            for q in parse_dcrust_paper(
                fake_docs[str((pyq_dir / e.local_relpath).resolve())],
                entry=e,
                course_code="CSE423C",
                subject_name="GREEN COMPUTING",
            )
            if q.unit == 1
        ],
        subject_name="GREEN COMPUTING",
    )
    assert clusters[0].session_count == 3  # Compiler Optimization asked in Dec24, Jun24, Dec23

    app = build_app(Settings(data_dir=tmp_path / "data", passphrase="test-vault-pass", llm_backend="extractive"))
    # Query A (with frequency ranking)
    ans_freq = app.orchestrator.handle(
        "Analyze the PYQ of CSE423C and give me all the PYQs asked from unit 1 in order of most frequently asked"
    )
    assert ans_freq.path == "S1" and [s.name for s in ans_freq.trace] == ["s1.guard.input", "s1.pyq_analyze"]
    assert "3 times" in ans_freq.text and "6 question" in ans_freq.text

    # Query B (without "most frequently" phrase — must STILL route to s1.pyq_analyze, NOT s1.pyq_lookup!)
    ans_unit1 = app.orchestrator.handle("Analyze the PYQ of CSE423C and give me all the PYQs asked from unit 1")
    assert [s.name for s in ans_unit1.trace] == ["s1.guard.input", "s1.pyq_analyze"]
    assert ans_unit1.ui_element is None
    assert "government initiatives" in ans_unit1.text.lower()

    # Query C (specific paper summary -> Compulsory + Unit I + Unit II all preserved)
    ans_sum = app.orchestrator.handle(
        "Summarize the key topics and important questions from CSE423C GREEN COMPUTING (June 2024)"
    )
    assert [s.name for s in ans_sum.trace] == ["s1.guard.input", "s1.pyq_analyze"]
    assert "Virtualization" in ans_sum.text and "Server Consolidation" in ans_sum.text

    # Standard catalog lookup still works via s1.pyq_lookup
    ans_cat = app.orchestrator.handle("Show PYQs for CSE423C")
    assert [s.name for s in ans_cat.trace] == ["s1.guard.input", "s1.pyq_lookup"]
    assert ans_cat.ui_element and ans_cat.ui_element["name"] == "DcrustPyqs"


