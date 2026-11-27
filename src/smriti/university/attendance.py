"""DCRUST attendance models, 75% bunk/attend math, a10dance.com formatting, and MHT/HTML parsing."""

from __future__ import annotations

import datetime as dt
import email
import html as html_lib
import quopri
import re
from dataclasses import dataclass, field


@dataclass
class AttendanceEntry:
    date: str
    time_slot: str
    status: str  # "PRESENT" | "ABSENT"


@dataclass
class SubjectAttendance:
    section_code: str
    course_code: str
    course_name: str
    attended: int
    total: int
    today_schedule: str = "No class today"
    last_marked: str = ""
    entries: list[AttendanceEntry] = field(default_factory=list)
    pyq_links: list[tuple[str, str]] = field(default_factory=list)

    @property
    def percentage(self) -> float:
        if self.total <= 0:
            return 0.0
        return round(100.0 * self.attended / self.total, 2)

    @property
    def percentage_str(self) -> str:
        pct = self.percentage
        if pct.is_integer():
            return f"{int(pct)}%"
        return f"{pct:.2f}".rstrip("0").rstrip(".") + "%"

    @property
    def status_level(self) -> str:
        """Matches a10dance.com color bands: >=75 success, 65..74.99 warning, <65 danger."""
        pct = self.percentage
        if pct >= 75.0:
            return "success"
        if pct >= 65.0:
            return "warning"
        return "danger"

    @property
    def prediction(self) -> str:
        return compute_bunk_or_need(self.attended, self.total)

    @property
    def display_name(self) -> str:
        if self.course_code and self.course_name:
            if self.course_name.upper().startswith(self.course_code.upper()):
                return self.course_name
            return f"{self.course_code} : {self.course_name}"
        return self.course_name or self.course_code or self.section_code


@dataclass
class AttendanceReport:
    roll_number: str
    semester_label: str
    fetched_at: str
    subjects: list[SubjectAttendance]
    student_name: str | None = None
    source_url: str = "https://dcrustm.samarth.edu.in/index.php/student-attendance/attendance/index"

    @property
    def total_attended(self) -> int:
        return sum(s.attended for s in self.subjects)

    @property
    def total_classes(self) -> int:
        return sum(s.total for s in self.subjects)

    @property
    def overall_percentage(self) -> float:
        if self.total_classes <= 0:
            return 0.0
        return round(100.0 * self.total_attended / self.total_classes, 2)

    @property
    def overall_percentage_str(self) -> str:
        pct = self.overall_percentage
        if pct.is_integer():
            return f"{int(pct)}%"
        return f"{pct:.2f}".rstrip("0").rstrip(".") + "%"


def compute_bunk_or_need(attended: int, total: int, threshold_num: int = 3, threshold_den: int = 4) -> str:
    """Exact integer 75% (3/4) prediction matching a10dance.com.

    If attended / total >= 3/4: max bunks b such that attended / (total + b) >= 3/4.
    Else: min consecutive classes x such that (attended + x) / (total + x) >= 3/4.
    """
    if total <= 0:
        return "No classes recorded yet"
    if attended * threshold_den >= threshold_num * total:
        bunk = (attended * threshold_den) // threshold_num - total
        if bunk <= 0:
            return "On 75% border — attend next class"
        return f"Safe to bunk {bunk} class{'es' if bunk != 1 else ''}"
    need = threshold_num * total - threshold_den * attended
    return f"Attend next {need} class{'es' if need != 1 else ''} for 75%"


def _progress_bar(pct: float, width: int = 10) -> str:
    filled = max(0, min(width, round(pct / 100.0 * width)))
    return "█" * filled + "░" * (width - filled)


def _status_dot(level: str) -> str:
    return {"success": "🟢", "warning": "🟡", "danger": "🔴"}.get(level, "⚪")


def format_attendance_markdown(report: AttendanceReport, *, include_entries: int = 3) -> str:
    """Render an AttendanceReport as a clean a10dance.com-style Markdown table + details."""
    if not report.subjects:
        return (
            f"### {report.semester_label} · {report.fetched_at}\n\n"
            f"No current-semester attendance records were found for roll number `{report.roll_number}` on Samarth."
        )

    overall_dot = _status_dot(
        "success" if report.overall_percentage >= 75 else ("warning" if report.overall_percentage >= 65 else "danger")
    )
    header_meta = f"Roll No: `{report.roll_number}`"
    if report.student_name and report.student_name != report.roll_number:
        header_meta = f"{report.student_name} · {header_meta}"

    lines = [
        f"### {report.semester_label} · {report.fetched_at}",
        (
            f"{header_meta} · Overall: {overall_dot} **{report.overall_percentage_str}** "
            f"(`{report.total_attended} / {report.total_classes}`)"
        ),
        "",
        "| Status | Subject | Code | Attendance | Progress | 75% Rule | Today's Schedule | Last Marked |",
        "| :---: | :--- | :--- | :---: | :--- | :--- | :--- | :---: |",
    ]

    for subj in report.subjects:
        dot = _status_dot(subj.status_level)
        bar = _progress_bar(subj.percentage)
        code = subj.section_code or subj.course_code or "—"
        today = subj.today_schedule or "No class today"
        last = subj.last_marked or "—"
        lines.append(
            f"| {dot} | **{subj.display_name}** | `{code}` | "
            f"**{subj.percentage_str}** (`{subj.attended} / {subj.total}`) | `{bar}` | "
            f"{subj.prediction} | {today} | {last} |"
        )

    extra_lines: list[str] = []
    for subj in report.subjects:
        details_parts: list[str] = []
        if include_entries > 0 and subj.entries:
            recent = subj.entries[:include_entries]
            rows = ", ".join(
                f"`{e.date}` ({e.time_slot}) {'● PRESENT' if e.status == 'PRESENT' else '○ ABSENT'}"
                for e in recent
            )
            details_parts.append(f"Recent: {rows}")
        if subj.pyq_links:
            shown = ", ".join(f"[{lbl}]({url})" if url.startswith("http") else lbl for lbl, url in subj.pyq_links[:4])
            details_parts.append(f"📄 PYQs: {shown}")
        if details_parts:
            extra_lines.append(f"- **{subj.course_code or subj.display_name}:** {' · '.join(details_parts)}")

    if extra_lines:
        lines.extend(["", "**Recent Lectures & PYQs:**", *extra_lines])

    return "\n".join(lines).strip()


def format_attendance_html(report: AttendanceReport) -> str:
    """Render a standalone dark-mode HTML attendance card page matching a10dance.com."""
    cards_html: list[str] = []
    for idx, subj in enumerate(report.subjects):
        color_var = f"var(--{subj.status_level})"
        width_pct = max(0, min(100, int(subj.percentage)))
        pyq_html = ""
        if subj.pyq_links:
            links = "".join(
                f'<a href="{html_lib.escape(url)}" target="_blank" rel="noopener noreferrer" class="pyq-chip">'
                f'⬇ {html_lib.escape(lbl)}</a>'
                for lbl, url in subj.pyq_links
            )
            pyq_html = (
                '<details style="margin-top:4px;margin-bottom:6px;font-size:0.75rem;">'
                '<summary style="color:var(--accent-color);font-weight:600;cursor:pointer;">'
                "📄 View Previous Year Papers</summary>"
                f'<div class="pyq-list">{links}</div></details>'
            )

        rows_html = "".join(
            '<div class="inner-details-row">'
            f'<div style="color:var(--text-color);">{html_lib.escape(e.date)}</div>'
            f'<div style="color:var(--text-muted-color);font-size:0.75rem;">{html_lib.escape(e.time_slot or "—")}</div>'
            f'<div class="{"status-present" if e.status == "PRESENT" else "status-absent"}">'
            f'{"● PRESENT" if e.status == "PRESENT" else "○ ABSENT"}</div>'
            "</div>"
            for e in subj.entries
        )
        if not rows_html:
            rows_html = '<div class="inner-details-row"><div style="opacity:0.6;">No lecture-by-lecture log returned by Samarth.</div></div>'

        cards_html.append(
            f"""
            <div class="subject-list-item" onclick="document.getElementById('details-{idx}').classList.toggle('open')">
                <div class="sl-main">
                    <div class="sl-left">
                        <div class="sl-code-row">
                            <span class="sl-dot" style="background:{color_var};box-shadow:0 0 6px {color_var};"></span>
                            <span class="sl-code">{html_lib.escape(subj.section_code or subj.course_code)}</span>
                        </div>
                        <div class="sl-name">{html_lib.escape(subj.display_name)}</div>
                    </div>
                    <div class="sl-right">
                        <div class="sl-perc" style="color:{color_var}">{html_lib.escape(subj.percentage_str)}</div>
                        <div class="sl-ratio">{subj.attended} / {subj.total}</div>
                    </div>
                </div>
                <div class="sl-prediction" style="color:{color_var}">
                    {pyq_html}
                    {html_lib.escape(subj.prediction)}
                </div>
                <div class="sl-meta">
                    <div>Today's Schedule: <strong style="color:var(--text-color)">{html_lib.escape(subj.today_schedule or "No class today")}</strong></div>
                    <div>Last attendance marked on: <strong style="color:var(--text-color)">{html_lib.escape(subj.last_marked or "—")}</strong></div>
                </div>
                <div class="sl-progress-container">
                    <div class="sl-progress-track">
                        <div class="sl-progress-fill" style="width:{width_pct}%;background:{color_var}"></div>
                    </div>
                </div>
                <div id="details-{idx}" class="subject-details-container">{rows_html}</div>
            </div>
            """
        )

    cards_joined = "\n".join(cards_html) or '<p style="padding:1.25rem;opacity:0.7;">No subjects found.</p>'
    student_line = f"{html_lib.escape(report.student_name)} · " if report.student_name else ""
    return f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DCRUST Attendance · {html_lib.escape(report.roll_number)}</title>
<style>
:root {{
  --bg-color:#0d0d10; --card-bg-color:rgba(30,30,35,0.65); --text-color:#ffffff;
  --text-muted-color:rgba(235,235,245,0.6); --border-color:rgba(255,255,255,0.15);
  --accent-color:#0A84FF; --present-text-color:#34C759; --absent-text-color:#FF453A;
  --danger:#FF453A; --success:#30D158; --warning:#FFD60A;
}}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:radial-gradient(circle at 50% 10%,#1c1c24 0%,var(--bg-color) 100%); color:var(--text-color); margin:0; display:flex; justify-content:center; min-height:100vh; padding:1.5rem 1rem; }}
.container {{ width:100%; max-width:42rem; background:var(--card-bg-color); border:1px solid var(--border-color); border-radius:1.5rem; padding:1.25rem 1.5rem; box-shadow:0 10px 30px rgba(0,0,0,0.5); }}
h1 {{ margin:0 0 0.25rem 0; font-size:1.35rem; }}
.subtitle {{ font-size:0.85rem; color:var(--text-muted-color); margin-bottom:1rem; }}
.results-container-div {{ background:rgba(255,255,255,0.02); border:1px solid var(--border-color); border-radius:1rem; overflow:hidden; }}
.sem-header {{ display:flex; justify-content:space-between; align-items:center; padding:1rem 1.25rem; border-bottom:1px solid var(--border-color); background:rgba(0,0,0,0.2); }}
.page-sem {{ font-weight:800; font-size:1.1rem; }}
.page-date {{ opacity:0.65; font-size:0.85rem; }}
.subject-list-item {{ padding:1rem 0 0.75rem; border-bottom:1px solid rgba(255,255,255,0.06); cursor:pointer; transition:background 0.2s; }}
.subject-list-item:hover {{ background:rgba(255,255,255,0.04); }}
.subject-list-item:last-child {{ border-bottom:none; }}
.sl-main {{ display:flex; justify-content:space-between; align-items:flex-start; padding:0 1.25rem; margin-bottom:0.5rem; }}
.sl-left {{ display:flex; flex-direction:column; gap:4px; flex:1; min-width:0; padding-right:1rem; }}
.sl-code-row {{ display:flex; align-items:center; gap:8px; }}
.sl-dot {{ width:8px; height:8px; border-radius:50%; display:inline-block; }}
.sl-code {{ font-size:0.75rem; color:var(--text-muted-color); font-family:monospace; letter-spacing:0.5px; }}
.sl-name {{ font-size:0.95rem; font-weight:600; line-height:1.3; }}
.sl-right {{ display:flex; flex-direction:column; align-items:flex-end; gap:2px; min-width:64px; }}
.sl-perc {{ font-size:1.2rem; font-weight:800; }}
.sl-ratio {{ font-size:0.75rem; color:var(--text-muted-color); font-weight:600; }}
.sl-prediction {{ font-size:0.78rem; font-weight:600; padding:0 1.25rem; margin-bottom:0.5rem; }}
.sl-meta {{ font-size:0.75rem; color:var(--text-muted-color); padding:0 1.25rem; margin-bottom:0.75rem; display:flex; flex-direction:column; gap:3px; }}
.sl-progress-container {{ padding:0 1.25rem; }}
.sl-progress-track {{ height:4px; background:rgba(255,255,255,0.1); border-radius:4px; overflow:hidden; width:100%; }}
.sl-progress-fill {{ height:100%; border-radius:4px; }}
.subject-details-container {{ background:rgba(0,0,0,0.2); overflow:hidden; max-height:0; transition:max-height 0.3s ease-out; }}
.subject-details-container.open {{ max-height:2000px; border-top:1px solid rgba(255,255,255,0.05); margin-top:0.75rem; }}
.inner-details-row {{ display:grid; grid-template-columns:1fr 1fr 1fr; padding:0.55rem 1.25rem; border-bottom:1px solid rgba(255,255,255,0.03); font-size:0.8rem; }}
.status-present {{ color:var(--present-text-color); font-weight:600; text-align:right; }}
.status-absent {{ color:var(--absent-text-color); font-weight:600; text-align:right; }}
.pyq-list {{ margin-top:6px; display:flex; flex-wrap:wrap; gap:6px; }}
.pyq-chip {{ color:var(--accent-color); text-decoration:none; border:1px solid var(--border-color); padding:2px 8px; border-radius:4px; font-size:0.72rem; }}
</style>
</head>
<body>
<div class="container">
  <h1>DCRUST Attendance · Smriti</h1>
  <div class="subtitle">{student_line}Roll No: {html_lib.escape(report.roll_number)} · Overall: <strong>{html_lib.escape(report.overall_percentage_str)}</strong> ({report.total_attended} / {report.total_classes}) · Click any subject to toggle lecture history</div>
  <div class="results-container-div">
    <div class="sem-header">
      <div class="page-sem">{html_lib.escape(report.semester_label)}</div>
      <div class="page-date">{html_lib.escape(report.fetched_at)}</div>
    </div>
    {cards_joined}
  </div>
</div>
</body>
</html>"""


def attendance_to_facts_and_chunks(report: AttendanceReport) -> tuple[list[tuple[int, str, str]], list[tuple[int, str, str]]]:
    """Convert an AttendanceReport into structured (page, attribute, value) facts & RAG chunks."""
    facts: list[tuple[int, str, str]] = [
        (1, "Overall Attendance", f"{report.overall_percentage_str} ({report.total_attended} / {report.total_classes})"),
        (1, "Attendance Semester", report.semester_label),
    ]
    for s in report.subjects:
        summary = f"{s.percentage_str} ({s.attended} / {s.total}) — {s.prediction}"
        bunk_or_need_attr = "classes safe to bunk" if s.percentage >= 75.0 else "classes needed for 75%"
        bunk_or_need_val = f"{s.prediction} ({s.percentage_str}, {s.attended}/{s.total})"
        if s.course_code:
            facts.append((1, f"{s.course_code} attendance", summary))
            facts.append((1, f"{s.course_code} {bunk_or_need_attr}", bunk_or_need_val))
            if s.last_marked:
                facts.append((1, f"{s.course_code} last attendance marked", s.last_marked))
        if s.course_name and s.course_name.upper() != s.course_code.upper():
            facts.append((1, f"{s.course_name} attendance", summary))
            facts.append((1, f"{s.course_name} {bunk_or_need_attr}", bunk_or_need_val))
            if s.last_marked:
                facts.append((1, f"{s.course_name} last attendance marked", s.last_marked))

    md = format_attendance_markdown(report, include_entries=20)
    chunks: list[tuple[int, str, str]] = [(1, md, "DCRUST Samarth Attendance")]
    return facts, chunks


def attendance_to_ui_props(report: AttendanceReport) -> dict:
    """Serialize an AttendanceReport for Chainlit's DcrustAttendance CustomElement."""
    return {
        "rollNumber": report.roll_number,
        "studentName": report.student_name or "",
        "semesterLabel": report.semester_label,
        "fetchedAt": report.fetched_at,
        "overallPercentage": report.overall_percentage_str,
        "totalAttended": report.total_attended,
        "totalClasses": report.total_classes,
        "subjects": [
            {
                "sectionCode": s.section_code,
                "courseCode": s.course_code,
                "courseName": s.course_name,
                "displayName": s.display_name,
                "attended": s.attended,
                "total": s.total,
                "percentage": s.percentage,
                "percentageStr": s.percentage_str,
                "statusLevel": s.status_level,
                "prediction": s.prediction,
                "todaySchedule": s.today_schedule or "No class today",
                "lastMarked": s.last_marked or "",
                "pyqLinks": [{"label": lbl, "url": url} for lbl, url in s.pyq_links],
                "entries": [
                    {"date": e.date, "timeSlot": e.time_slot, "status": e.status}
                    for e in s.entries
                ],
            }
            for s in report.subjects
        ],
    }


def _decode_mht_html(raw: str) -> str:
    """Extract and decode the primary text/html part if `raw` is an MHT/MHTML archive."""
    if "MultipartBoundary" not in raw and "Content-Type: text/html" not in raw:
        return raw
    msg = email.message_from_string(raw)
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload is not None:
                    return payload.decode("utf-8", errors="replace")
                return quopri.decodestring(part.get_payload()).decode("utf-8", errors="replace")
    return raw


def parse_a10dance_html(raw: str, *, roll_number: str = "unknown") -> AttendanceReport:
    """Parse an a10dance.com HTML or saved MHT snapshot (like DCRUST Attendance Checker.mht)."""
    doc = _decode_mht_html(raw)
    sem_m = re.search(r'<div class="page-sem">\s*(.*?)\s*</div>', doc, re.DOTALL)
    date_m = re.search(r'<div class="page-date">\s*(.*?)\s*</div>', doc, re.DOTALL)
    semester = html_lib.unescape(" ".join(sem_m.group(1).split())) if sem_m else "Current Semester"
    today_str = dt.datetime.now(tz=dt.timezone.utc).astimezone().date().strftime("%a, %b %d")
    fetched_at = html_lib.unescape(" ".join(date_m.group(1).split())) if date_m else today_str

    subjects: list[SubjectAttendance] = []
    for block in doc.split('<div class="subject-list-item')[1:]:
        code_m = re.search(r'<span class="sl-code">\s*(.*?)\s*</span>', block, re.DOTALL)
        name_m = re.search(r'<div class="sl-name">\s*(.*?)\s*</div>', block, re.DOTALL)
        ratio_m = re.search(r'<div class="sl-ratio">\s*(\d+)\s*/\s*(\d+)\s*</div>', block, re.DOTALL)
        if not name_m or not ratio_m:
            continue
        section_code = html_lib.unescape(code_m.group(1).strip()) if code_m else ""
        full_name = html_lib.unescape(" ".join(name_m.group(1).split()))
        if ":" in full_name:
            c_code, c_name = (part.strip() for part in full_name.split(":", 1))
        else:
            c_code, c_name = section_code, full_name
        attended, total = int(ratio_m.group(1)), int(ratio_m.group(2))

        sched_m = re.search(r"Today's Schedule:\s*(.*?)(?:</div>)", block, re.DOTALL)
        today_schedule = " ".join(re.sub(r"<[^>]+>", " ", sched_m.group(1)).split()) if sched_m else "No class today"
        last_m = re.search(r"Last attendance marked on:\s*<strong[^>]*>\s*(.*?)\s*</strong>", block, re.DOTALL)
        last_marked = html_lib.unescape(last_m.group(1).strip()) if last_m else ""

        pyq_links: list[tuple[str, str]] = []
        for href, lbl in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL):
            clean_lbl = html_lib.unescape(" ".join(re.sub(r"<[^>]+>", " ", lbl).split()))
            clean_lbl = re.sub(r"^(?:⬇|\\u2b07)\s*", "", clean_lbl).strip()
            if href and clean_lbl:
                pyq_links.append((clean_lbl, href))

        entries: list[AttendanceEntry] = []
        for row_m in re.finditer(r'<div class="inner-details-row">(.*?)</div>\s*</div>', block, re.DOTALL):
            row_html = row_m.group(1)
            divs = re.findall(r"<div[^>]*>(.*?)</div>", row_html, re.DOTALL)
            if len(divs) >= 2:
                date_str = html_lib.unescape(" ".join(divs[0].split()))
                time_str = html_lib.unescape(" ".join(divs[1].split()))
                status = "PRESENT" if "PRESENT" in row_html.upper() else "ABSENT"
                entries.append(AttendanceEntry(date=date_str, time_slot=time_str, status=status))

        subjects.append(
            SubjectAttendance(
                section_code=section_code,
                course_code=c_code,
                course_name=c_name,
                attended=attended,
                total=total,
                today_schedule=today_schedule or "No class today",
                last_marked=last_marked,
                entries=entries,
                pyq_links=pyq_links,
            )
        )

    return AttendanceReport(
        roll_number=roll_number,
        semester_label=semester,
        fetched_at=fetched_at,
        subjects=subjects,
    )
