"""DCRUST eSamarth portal client, HTML parsers, encrypted credential storage, and RAG sync."""

from __future__ import annotations

import datetime as dt
import hashlib
import http.cookiejar
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

from smriti.graph import KnowledgeGraph
from smriti.guardrails.pii import redact
from smriti.storage import Database
from smriti.university.attendance import (
    AttendanceEntry,
    AttendanceReport,
    SubjectAttendance,
    attendance_to_facts_and_chunks,
    format_attendance_html,
)
from smriti.university.timetable import (
    TimetableReport,
    build_timetable_report,
    format_timetable_html,
    timetable_to_facts_and_chunks,
)
from smriti.vault import Vault, VaultLockedError, WrongPassphraseError

SAMARTH_BASE_URL = "https://dcrustm.samarth.edu.in"
LOGIN_PATH = "/index.php/site/login"
ATTENDANCE_PATH = "/index.php/student-attendance/attendance/index"
TIMETABLE_PATH = "/index.php/student-attendance/attendance/view-time-table"
SAMARTH_CREDS_VAULT_NAME = "samarth_creds"
SAMARTH_DOC_TITLE = "DCRUST Samarth Attendance"
SAMARTH_TIMETABLE_DOC_TITLE = "DCRUST Samarth Timetable"

_COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)
_DATE_YMD = re.compile(r"\b(\d{4})[-/](\d{2})[-/](\d{2})\b")
_DATE_DMY = re.compile(r"\b(\d{2})[-/.](\d{2})[-/.](\d{4})\b")
_TIME_SLOT = re.compile(r"\b(\d{1,2}:\d{2}(?:\s*[AP]M)?\s*[-–to]+\s*\d{1,2}:\d{2}(?:\s*[AP]M)?)\b", re.IGNORECASE)
_COURSE_CODE = re.compile(r"\b([A-Z]{2,5}\d{2,4}[A-Z]{0,3})\b")


class SamarthError(RuntimeError):
    """Base error for DCRUST Samarth integration."""


class SamarthAuthError(SamarthError):
    """Raised when roll number or password is rejected by Samarth."""


class SamarthCaptchaError(SamarthError):
    """Raised when the portal requires interactive CAPTCHA verification."""


class SamarthConnectionError(SamarthError):
    """Raised when Samarth cannot be reached or returns an unexpected HTTP failure."""


def _extract_csrf_token(html_text: str) -> str | None:
    clean = _COMMENTS.sub("", html_text)
    for pat in (
        r'<input[^>]+name=["\']_csrf["\'][^>]+value=["\']([^"\']+)["\']',
        r'<input[^>]+value=["\']([^"\']+)["\'][^>]+name=["\']_csrf["\']',
        r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']',
    ):
        m = re.search(pat, clean, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _has_active_captcha(html_text: str) -> bool:
    """Detect active (uncommented) CAPTCHA widgets on the login form."""
    clean = _COMMENTS.sub("", html_text)
    return bool(
        re.search(
            r'id=["\']loginform-verifycode|name=["\']LoginForm\[verifyCode\]|'
            r'class=["\'][^"\']*(?:g-recaptcha|h-captcha|cf-turnstile)',
            clean,
            re.IGNORECASE,
        )
    )


def _normalize_date(text: str) -> str | None:
    m = _DATE_YMD.search(text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = _DATE_DMY.search(text)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


class _TableParser(HTMLParser):
    """Extracts HTML tables into structured rows with text + links per cell."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[tuple[str, list[str]]]]] = []
        self._in_table = False
        self._table: list[list[tuple[str, list[str]]]] = []
        self._row: list[tuple[str, list[str]]] | None = None
        self._in_cell = False
        self._is_header = False
        self._cell_text: list[str] = []
        self._cell_links: list[str] = []
        self._row_headers: list[bool] = []
        self.header_rows: list[set[int]] = []

    def _flush_row(self) -> None:
        if self._row is not None:
            if self._row:
                if any(self._row_headers):
                    self._header_set.add(len(self._table))
                self._table.append(self._row)
            self._row = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "table":
            self._in_table = True
            self._table = []
            self._header_set: set[int] = set()
            self._row = None
        elif self._in_table and tag in ("tr", "thead"):
            self._flush_row()
            self._row = []
            self._row_headers = []
        elif self._in_table and tag in ("td", "th"):
            if self._row is None:
                self._row = []
                self._row_headers = []
            self._in_cell = True
            self._is_header = tag == "th"
            self._cell_text = []
            self._cell_links = []
        elif self._in_cell and tag == "a" and attr_map.get("href"):
            self._cell_links.append(attr_map["href"] or "")

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._in_cell and tag in ("td", "th"):
            text = " ".join("".join(self._cell_text).split())
            if self._row is not None:
                self._row.append((text, list(self._cell_links)))
                self._row_headers.append(self._is_header)
            self._in_cell = False
        elif self._in_table and tag in ("tr", "thead"):
            self._flush_row()
        elif self._in_table and tag == "table":
            self._flush_row()
            if self._table:
                self.tables.append(self._table)
                self.header_rows.append(self._header_set)
            self._in_table = False


def _split_course_code_name(raw_course: str, raw_code: str = "") -> tuple[str, str]:
    course = " ".join(raw_course.split()).strip()
    code = " ".join(raw_code.split()).strip()
    if ":" in course and not code:
        left, right = (p.strip() for p in course.split(":", 1))
        return left, right
    if ":" in course and code:
        left, right = (p.strip() for p in course.split(":", 1))
        if left.upper() == code.upper():
            return code, right
    m = re.match(r"^([A-Z]{2,5}-?\d{2,4}[A-Z]{0,3})\s*[-–:]\s*(.+)$", course)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    if not code:
        cm = _COURSE_CODE.search(course)
        if cm:
            code = cm.group(1)
    return code, course


def _parse_ratio_or_counts(texts: list[str]) -> tuple[int, int] | None:
    for t in texts:
        m = re.search(r"\b(\d+)\s*/\s*(\d+)\b", t)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def _term_sort_key(year_str: str, term_str: str) -> tuple[int, int, int]:
    years = [int(y) for y in re.findall(r"\d{4}", year_str)]
    y_start = years[0] if years else 0
    y_end = years[1] if len(years) > 1 else y_start
    sem_m = re.search(r"(\d+)", term_str)
    sem_num = int(sem_m.group(1)) if sem_m else 0
    return (y_start, y_end, sem_num)


def _format_semester_label(year_str: str, term_str: str, fallback: str) -> str:
    sem_m = re.search(r"(\d+)", term_str)
    if sem_m and year_str:
        return f"Semester {sem_m.group(1)} ({year_str.strip()})"
    if term_str and year_str:
        return f"{term_str.strip()} ({year_str.strip()})"
    return term_str.strip() or year_str.strip() or fallback


def parse_samarth_attendance_index(
    html_text: str,
    *,
    current_only: bool = True,
) -> tuple[str, str | None, list[tuple[SubjectAttendance, str | None]]]:
    """Parse Samarth `/student-attendance/attendance/index` HTML.

    Filters to only the latest (Academic Year, Semester) when term/year columns exist and `current_only=True`.
    Returns (semester_label, student_name, [(SubjectAttendance, detail_href_or_None), ...]).
    """
    clean = _COMMENTS.sub("", html_text)
    sem_m = re.search(
        r"\b((?:Odd|Even)\s+Sem(?:ester)?\s+\d{4}|Sem(?:ester)?\s*[I1-8Vv]+(?:\s*\(\d{4}[-–]\d{2,4}\))?|\d{4}[-–]\d{2,4})\b",
        clean,
        re.IGNORECASE,
    )
    fallback_sem = sem_m.group(1).strip() if sem_m else "Current Semester"

    name_m = re.search(
        r'(?:class=["\'][^"\']*(?:user-name|student-name|profile-name)[^"\']*["\'][^>]*>|Welcome,?\s*)'
        r"\s*([A-Z][A-Za-z .]{2,40})",
        clean,
    )
    student_name = name_m.group(1).strip() if name_m else None
    if student_name and re.fullmatch(r"[\d\s]+", student_name):
        student_name = None

    tp = _TableParser()
    tp.feed(clean)

    parsed_rows: list[tuple[tuple[int, int, int], str, str, SubjectAttendance, str | None]] = []
    for table_idx, table in enumerate(tp.tables):
        headers = tp.header_rows[table_idx]
        col_map: dict[str, int] = {}
        data_start = 0
        if 0 in headers:
            data_start = 1
            for col_i, (hdr_txt, _) in enumerate(table[0]):
                h = hdr_txt.lower()
                if any(k in h for k in ("course code", "paper code", "subject code")):
                    col_map.setdefault("code", col_i)
                elif any(k in h for k in ("course", "subject", "paper", "title")):
                    col_map.setdefault("name", col_i)
                elif any(k in h for k in ("batch", "section", "class", "group")):
                    col_map.setdefault("section", col_i)
                elif any(k in h for k in ("term", "semester")):
                    col_map.setdefault("term", col_i)
                elif "year" in h or "session" in h:
                    col_map.setdefault("year", col_i)
                elif any(k in h for k in ("present", "attended")):
                    col_map.setdefault("attended", col_i)
                elif any(k in h for k in ("total", "held", "delivered", "classes")):
                    col_map.setdefault("total", col_i)
                elif "%" in h or "percent" in h:
                    col_map.setdefault("pct", col_i)

        for row_i in range(data_start, len(table)):
            if row_i in headers:
                continue
            row = table[row_i]
            cell_texts = [c[0] for c in row]
            if not any(cell_texts):
                continue
            links = [href for _, hrefs in row for href in hrefs]
            detail_link = next(
                (h for h in links if "attendance" in h.lower() and ("view" in h.lower() or "detail" in h.lower() or "id=" in h.lower())),
                links[0] if links else None,
            )

            raw_code = cell_texts[col_map["code"]] if "code" in col_map and col_map["code"] < len(cell_texts) else ""
            raw_name = cell_texts[col_map["name"]] if "name" in col_map and col_map["name"] < len(cell_texts) else ""
            section_code = cell_texts[col_map["section"]] if "section" in col_map and col_map["section"] < len(cell_texts) else ""
            term_str = cell_texts[col_map["term"]] if "term" in col_map and col_map["term"] < len(cell_texts) else ""
            year_str = cell_texts[col_map["year"]] if "year" in col_map and col_map["year"] < len(cell_texts) else ""

            if not raw_name:
                candidates = [
                    t for t in cell_texts
                    if t and not re.fullmatch(r"[\d./%\s]+", t) and t.lower() not in {"view", "details", "check"}
                ]
                if not candidates:
                    continue
                if len(candidates) >= 2 and _COURSE_CODE.fullmatch(candidates[0]):
                    raw_code = raw_code or candidates[0]
                    raw_name = candidates[1]
                else:
                    raw_name = max(candidates, key=len)

            c_code, c_name = _split_course_code_name(raw_name, raw_code)
            if not c_name and not c_code:
                continue

            attended, total = 0, 0
            if "attended" in col_map and "total" in col_map:
                att_m = re.search(r"\d+", cell_texts[col_map["attended"]])
                tot_m = re.search(r"\d+", cell_texts[col_map["total"]])
                if att_m and tot_m:
                    attended, total = int(att_m.group(0)), int(tot_m.group(0))
            if total == 0:
                ratio = _parse_ratio_or_counts(cell_texts)
                if ratio:
                    attended, total = ratio

            if not detail_link and total == 0:
                continue

            sort_key = _term_sort_key(year_str, term_str)
            parsed_rows.append(
                (
                    sort_key,
                    year_str,
                    term_str,
                    SubjectAttendance(
                        section_code=section_code or c_code,
                        course_code=c_code,
                        course_name=c_name,
                        attended=attended,
                        total=total,
                    ),
                    detail_link,
                )
            )
        if parsed_rows:
            break

    if not parsed_rows:
        return fallback_sem, student_name, []

    latest_key = max(r[0] for r in parsed_rows)
    if current_only and latest_key != (0, 0, 0):
        filtered = [r for r in parsed_rows if r[0] == latest_key]
    else:
        filtered = parsed_rows

    semester = _format_semester_label(filtered[0][1], filtered[0][2], fallback_sem)
    return semester, student_name, [(r[3], r[4]) for r in filtered]


def parse_samarth_attendance_detail(html_text: str) -> tuple[list[AttendanceEntry], int | None, int | None]:
    """Parse a Samarth `view-attendance` page into sorted lecture entries + summary (attended, total)."""
    clean = _COMMENTS.sub("", html_text)
    tp = _TableParser()
    tp.feed(clean)

    # First check Samarth summary detail-view:
    # "Total Classes Taken: 38, Present Count: 32, Absent Count: 6, Leave Count: 0"
    summary_att: int | None = None
    summary_tot: int | None = None
    tot_m = re.search(r"Total\s+Classes\s+Taken\s*[:\-]?\s*(\d+)", clean, re.IGNORECASE)
    att_m = re.search(r"Present\s+Count\s*[:\-]?\s*(\d+)", clean, re.IGNORECASE)
    if tot_m and att_m:
        summary_tot = int(tot_m.group(1))
        summary_att = int(att_m.group(1))
    else:
        ratio_m = re.search(r"(?:Attended|Present)\s*[:\-]?\s*(\d+)\s*/\s*(\d+)", clean, re.IGNORECASE)
        if ratio_m:
            summary_att = int(ratio_m.group(1))
            summary_tot = int(ratio_m.group(2))

    entries: list[AttendanceEntry] = []
    for table_idx, table in enumerate(tp.tables):
        headers = tp.header_rows[table_idx]
        for row_i, row in enumerate(table):
            if row_i in headers:
                continue
            texts = [c[0] for c in row]
            joined = " ".join(texts)
            date_str = _normalize_date(joined)
            if not date_str:
                continue
            time_m = _TIME_SLOT.search(joined)
            time_slot = time_m.group(1) if time_m else ""
            upper = joined.upper()
            if re.search(r"\b(ABSENT|AB)\b", upper):
                status = "ABSENT"
            elif re.search(r"\b(PRESENT|PR)\b", upper):
                status = "PRESENT"
            else:
                continue
            entries.append(AttendanceEntry(date=date_str, time_slot=time_slot, status=status))

    entries.sort(key=lambda e: (e.date, e.time_slot), reverse=True)
    if summary_tot is not None:
        return entries, summary_att or 0, summary_tot
    if entries:
        att = sum(1 for e in entries if e.status == "PRESENT")
        return entries, att, len(entries)
    return [], None, None


def parse_samarth_timetable(html_text: str, *, weekday: str | None = None) -> dict[str, str]:
    """Extract today's schedule per course code from `/student-attendance/attendance/view-time-table`."""
    day = (weekday or dt.datetime.now(tz=dt.timezone.utc).astimezone().strftime("%A")).lower()
    day_short = day[:3]
    clean = _COMMENTS.sub("", html_text)
    tp = _TableParser()
    tp.feed(clean)

    schedule: dict[str, list[str]] = {}
    for table in tp.tables:
        for row in table:
            texts = [c[0] for c in row]
            joined = " ".join(texts)
            lower = joined.lower()
            if not (day in lower or re.search(rf"\b{re.escape(day_short)}\b", lower)):
                continue
            time_m = _TIME_SLOT.search(joined)
            time_str = time_m.group(1) if time_m else "Scheduled today"
            for code in _COURSE_CODE.findall(joined.upper()):
                schedule.setdefault(code, [])
                if time_str not in schedule[code]:
                    schedule[code].append(time_str)
    return {k: ", ".join(v) for k, v in schedule.items()}


def parse_samarth_timetable_api(events: list[dict], *, target_date: dt.date | None = None) -> dict[str, str]:
    """Extract today's class schedule per course code from Samarth `get-classes-of-student` JSON."""
    today = target_date or dt.datetime.now(tz=dt.timezone.utc).astimezone().date()
    tz = dt.datetime.now(tz=dt.timezone.utc).astimezone().tzinfo
    schedule: dict[str, list[str]] = {}
    for ev in events:
        start_ts = ev.get("start")
        end_ts = ev.get("end")
        if not isinstance(start_ts, (int, float)):
            continue
        start_dt = dt.datetime.fromtimestamp(start_ts, tz=tz)
        if start_dt.date() != today:
            continue
        slot = start_dt.strftime("%H:%M")
        if isinstance(end_ts, (int, float)):
            end_dt = dt.datetime.fromtimestamp(end_ts, tz=tz)
            slot = f"{slot} - {end_dt.strftime('%H:%M')}"
        desc = f"{ev.get('title', '')} {ev.get('desc', '')}".upper()
        for code in _COURSE_CODE.findall(desc):
            schedule.setdefault(code, [])
            if slot not in schedule[code]:
                schedule[code].append(slot)
    return {k: ", ".join(v) for k, v in schedule.items()}


class SamarthClient:
    """HTTP client for DCRUST Samarth student portal using Python stdlib cookies + TLS."""

    def __init__(self, base_url: str = SAMARTH_BASE_URL, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _build_opener(self) -> urllib.request.OpenerDirector:
        jar = http.cookiejar.CookieJar()
        ctx = ssl.create_default_context()
        return urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar),
            urllib.request.HTTPSHandler(context=ctx),
        )

    def _fetch(self, opener: urllib.request.OpenerDirector, url_or_path: str,
               data: bytes | None = None) -> tuple[str, str]:
        url = urllib.parse.urljoin(self.base_url + "/", url_or_path)
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Smriti/0.1)"}
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                return resp.geturl(), resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SamarthConnectionError(f"Could not reach DCRUST Samarth ({url}): {exc}") from exc

    @staticmethod
    def _with_query_params(href: str, **updates: str) -> str:
        parsed = urllib.parse.urlsplit(href)
        qs = dict(urllib.parse.parse_qsl(parsed.query))
        qs.update(updates)
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(qs), parsed.fragment)
        )

    def _login_session(self, roll_number: str, password: str) -> urllib.request.OpenerDirector:
        roll = roll_number.strip()
        if not roll or not password:
            raise SamarthAuthError("Both eSamarth roll number and password are required.")

        opener = self._build_opener()
        login_url, login_html = self._fetch(opener, LOGIN_PATH)
        if _has_active_captcha(login_html):
            raise SamarthCaptchaError(
                "DCRUST Samarth is currently requiring CAPTCHA verification on login. "
                "Please sign in directly in your browser (https://dcrustm.samarth.edu.in)."
            )

        csrf = _extract_csrf_token(login_html)
        form: dict[str, str] = {
            "LoginForm[username]": roll,
            "LoginForm[password]": password,
            "login-button": "",
        }
        if csrf:
            form["_csrf"] = csrf
        encoded = urllib.parse.urlencode(form).encode("utf-8")
        post_url, post_html = self._fetch(opener, login_url, data=encoded)

        if "/site/login" in post_url or 'id="login-form"' in post_html:
            err_m = re.search(r'<p class="help-block help-block-error"[^>]*>([^<]+)</p>', post_html)
            reason = err_m.group(1).strip() if err_m and err_m.group(1).strip() else "Invalid roll number or password."
            raise SamarthAuthError(f"Samarth login failed: {reason}")
        return opener

    def _fetch_timetable_events(self, opener: urllib.request.OpenerDirector) -> tuple[str, list[dict]]:
        _, tt_html = self._fetch(opener, TIMETABLE_PATH)
        sid_m = re.search(r'data-student-id=["\']([^"\']+)["\']', tt_html)
        api_m = re.search(r'data-get-all-classes-of-student=["\']([^"\']+)["\']', tt_html)
        if sid_m and api_m:
            api_url = self._with_query_params(api_m.group(1), student_id=sid_m.group(1))
            _, api_body = self._fetch(opener, api_url)
            payload = json.loads(api_body)
            if isinstance(payload.get("data"), list):
                return tt_html, payload["data"]
        return tt_html, []

    def fetch_attendance(self, roll_number: str, password: str, *, current_only: bool = True) -> AttendanceReport:
        roll = roll_number.strip()
        opener = self._login_session(roll, password)

        att_url, att_html = self._fetch(opener, ATTENDANCE_PATH)
        if "/site/login" in att_url:
            raise SamarthAuthError("Samarth session expired before reading attendance.")

        semester, student_name, subject_rows = parse_samarth_attendance_index(att_html, current_only=current_only)

        # Fetch today's schedule via timetable HTML + embedded student JSON endpoint (fail-soft)
        today_map: dict[str, str] = {}
        try:
            tt_html, raw_events = self._fetch_timetable_events(opener)
            today_map = parse_samarth_timetable(tt_html)
            if raw_events:
                today_map.update(parse_samarth_timetable_api(raw_events))
        except (SamarthError, json.JSONDecodeError, ValueError):
            pass

        def _enrich(item: tuple[SubjectAttendance, str | None]) -> SubjectAttendance:
            subj, href = item
            if href:
                try:
                    sorted_href = self._with_query_params(href, sort="-attendance_date")
                    _, det_html = self._fetch(opener, sorted_href)
                    entries, att_det, tot_det = parse_samarth_attendance_detail(det_html)
                    if tot_det and len(entries) < tot_det and "page=" not in sorted_href:
                        # Fetch remaining pages (typically 1-2 extra pages) to keep full history in export
                        seen = {(e.date, e.time_slot, e.status) for e in entries}
                        page_num = 2
                        while len(entries) < tot_det and page_num <= 5:
                            _, pg_html = self._fetch(opener, self._with_query_params(sorted_href, page=str(page_num)))
                            more, _, _ = parse_samarth_attendance_detail(pg_html)
                            new_rows = [e for e in more if (e.date, e.time_slot, e.status) not in seen]
                            if not new_rows:
                                break
                            seen.update((e.date, e.time_slot, e.status) for e in new_rows)
                            entries.extend(new_rows)
                            page_num += 1
                        entries.sort(key=lambda e: (e.date, e.time_slot), reverse=True)
                    if entries:
                        subj.entries = entries
                        subj.last_marked = entries[0].date
                    if tot_det is not None and (subj.total == 0 or tot_det >= subj.total):
                        subj.attended = att_det or 0
                        subj.total = tot_det
                except SamarthError:
                    pass
            if subj.course_code.upper() in today_map:
                subj.today_schedule = today_map[subj.course_code.upper()]
            return subj

        if any(href for _, href in subject_rows):
            with ThreadPoolExecutor(max_workers=6) as pool:
                subjects = list(pool.map(_enrich, subject_rows))
        else:
            subjects = [_enrich(item) for item in subject_rows]

        return AttendanceReport(
            roll_number=roll,
            student_name=student_name,
            semester_label=semester,
            fetched_at=dt.datetime.now(tz=dt.timezone.utc).astimezone().strftime("%a, %b %d"),
            subjects=subjects,
            source_url=att_url,
        )

    def fetch_timetable(self, roll_number: str, password: str, *, current_only: bool = True) -> TimetableReport:
        roll = roll_number.strip()
        opener = self._login_session(roll, password)
        att_url, att_html = self._fetch(opener, ATTENDANCE_PATH)
        if "/site/login" in att_url:
            raise SamarthAuthError("Samarth session expired before reading timetable.")
        semester, _, subject_rows = parse_samarth_attendance_index(att_html, current_only=current_only)
        current_ids: set[str] | None = None
        if current_only:
            extracted: set[str] = set()
            for _, href in subject_rows:
                if href:
                    qs = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(href).query))
                    if qs.get("class_id"):
                        extracted.add(qs["class_id"])
            if extracted:
                current_ids = extracted
        try:
            _, raw_events = self._fetch_timetable_events(opener)
        except (json.JSONDecodeError, ValueError) as exc:
            raise SamarthConnectionError(f"Unexpected timetable payload from Samarth: {exc}") from exc
        return build_timetable_report(roll, semester, raw_events, current_class_ids=current_ids)


# ---- encrypted credential vault helpers ----------------------------------------------------
def save_samarth_credentials(vault: Vault, roll_number: str, password: str) -> None:
    """Encrypt and store eSamarth roll number & password in the Vault (AES-256-GCM)."""
    payload = json.dumps({"roll_number": roll_number.strip(), "password": password}).encode("utf-8")
    vault.put(SAMARTH_CREDS_VAULT_NAME, payload)


def load_samarth_credentials(vault: Vault) -> tuple[str, str] | None:
    """Load eSamarth credentials from the encrypted Vault (or SMRITI_SAMARTH_* env vars)."""
    creds_path = vault.dir / f"{SAMARTH_CREDS_VAULT_NAME}.enc"
    if creds_path.exists() and vault.unlocked:
        try:
            raw = vault.get(f"{SAMARTH_CREDS_VAULT_NAME}.enc")
            data = json.loads(raw.decode("utf-8"))
            if data.get("roll_number") and data.get("password"):
                return str(data["roll_number"]), str(data["password"])
        except (WrongPassphraseError, ValueError, KeyError):
            pass
    env_u = os.environ.get("SMRITI_SAMARTH_USER", "").strip()
    env_p = os.environ.get("SMRITI_SAMARTH_PASSWORD", "")
    if env_u and env_p:
        return env_u, env_p
    return None


def clear_samarth_credentials(vault: Vault) -> bool:
    creds_path = vault.dir / f"{SAMARTH_CREDS_VAULT_NAME}.enc"
    if creds_path.exists():
        creds_path.unlink()
        return True
    return False


# ---- RAG indexing + HTML dashboard sync ----------------------------------------------------
def _attach_local_pyqs(db: Database, report: AttendanceReport, pyq_dir: Path | None = None) -> None:
    docs = [d for d in db.list_documents() if d["doc_type"] == "past_paper"]
    seen_urls: dict[str, set[str]] = {}
    for subj in report.subjects:
        code = subj.course_code.upper()
        if not code:
            continue
        bucket = seen_urls.setdefault(code, set())
        for d in docs:
            hay = f"{d['title']} {d['course'] or ''}".upper()
            if code in hay and d["path"] not in bucket:
                bucket.add(d["path"])
                subj.pyq_links.append((f"{d['title']} (local PYQ)", d["path"]))

    if pyq_dir is not None:
        from smriti.university.pyq import load_pyq_catalog

        cat = load_pyq_catalog(pyq_dir)
        if cat:
            by_code: dict[str, list] = {}
            for e in cat.entries:
                by_code.setdefault(e.course_code.upper(), []).append(e)
            for subj in report.subjects:
                code = subj.course_code.upper()
                if not code or code not in by_code:
                    continue
                bucket = seen_urls.setdefault(code, set())
                for e in sorted(by_code[code], key=lambda x: -x.session_sort):
                    if e.status == "missing_remote" or e.remote_url in bucket:
                        continue
                    bucket.add(e.remote_url)
                    subj.pyq_links.append((f"{e.session_label} ({e.course_code})", e.remote_url))


def _resolve_credentials(vault: Vault, roll_number: str | None, password: str | None) -> tuple[str, str]:
    creds = (roll_number.strip(), password) if (roll_number and password) else load_samarth_credentials(vault)
    if creds is None:
        raise SamarthAuthError(
            "No eSamarth credentials found. Provide your roll number and password, or run `smriti attendance --login`."
        )
    return creds


def _store_samarth_snapshot(
    db: Database,
    vault: Vault,
    data_dir: Path,
    *,
    title: str,
    roll: str,
    snapshot_obj: dict,
    facts: list[tuple[int, str, str]],
    chunks: list[tuple[int, str, str]],
    export_prefix: str,
    html_body: str,
) -> Path:
    for existing in db.list_documents():
        if existing["title"] == title:
            db.delete_document(existing["id"])

    snapshot = json.dumps(snapshot_obj, sort_keys=True).encode("utf-8")
    sha = hashlib.sha256(snapshot + str(dt.datetime.now(tz=dt.timezone.utc).timestamp()).encode()).hexdigest()

    vault_file = None
    sensitive = vault.unlocked
    if sensitive:
        try:
            vault_file = vault.put(f"{export_prefix}_{sha[:12]}", snapshot)
        except VaultLockedError:
            sensitive = False

    safe_chunks = [(p, redact(txt) if sensitive else txt, topic) for p, txt, topic in chunks]
    doc_id = db.add_document(
        title=title,
        path=f"samarth:{roll}",
        sha256=sha,
        kind="personal",
        doc_type="timetable",
        course=None,
        semester=None,
        sensitive=sensitive,
        vault_file=vault_file,
    )
    db.add_chunks(doc_id, safe_chunks)
    db.add_facts(doc_id, facts)
    KnowledgeGraph(db).rebuild()

    exports_dir = Path(data_dir) / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    safe_roll = re.sub(r"[^A-Za-z0-9_-]", "", roll) or "student"
    html_path = exports_dir / f"{export_prefix}_{safe_roll}.html"
    html_path.write_text(html_body, encoding="utf-8")
    return html_path


def sync_samarth_attendance(
    db: Database,
    vault: Vault,
    data_dir: Path,
    *,
    roll_number: str | None = None,
    password: str | None = None,
    save_creds: bool = True,
    client: SamarthClient | None = None,
) -> tuple[AttendanceReport, Path]:
    """Fetch live attendance from DCRUST Samarth, index into Smriti RAG, and export HTML card report."""
    roll, pwd = _resolve_credentials(vault, roll_number, password)
    client = client or SamarthClient()
    report = client.fetch_attendance(roll, pwd)
    from smriti.config import Settings

    _attach_local_pyqs(db, report, Settings(data_dir=Path(data_dir)).pyq_dir)

    if save_creds and vault.unlocked:
        save_samarth_credentials(vault, roll, pwd)

    facts, chunks = attendance_to_facts_and_chunks(report)
    snapshot_obj = {
        "roll_number": report.roll_number,
        "semester_label": report.semester_label,
        "fetched_at": report.fetched_at,
        "subjects": [
            {
                "section_code": s.section_code,
                "course_code": s.course_code,
                "course_name": s.course_name,
                "attended": s.attended,
                "total": s.total,
                "last_marked": s.last_marked,
            }
            for s in report.subjects
        ],
    }
    html_path = _store_samarth_snapshot(
        db,
        vault,
        data_dir,
        title=SAMARTH_DOC_TITLE,
        roll=roll,
        snapshot_obj=snapshot_obj,
        facts=facts,
        chunks=chunks,
        export_prefix="dcrust_attendance",
        html_body=format_attendance_html(report),
    )
    db.audit("attendance", f"samarth sync roll={roll} subjects={len(report.subjects)} overall={report.overall_percentage_str}")
    return report, html_path


def sync_samarth_timetable(
    db: Database,
    vault: Vault,
    data_dir: Path,
    *,
    roll_number: str | None = None,
    password: str | None = None,
    save_creds: bool = True,
    client: SamarthClient | None = None,
) -> tuple[TimetableReport, Path]:
    """Fetch current-semester Weekly Timetable + Calendar from Samarth, index into RAG, and export HTML."""
    roll, pwd = _resolve_credentials(vault, roll_number, password)
    client = client or SamarthClient()
    report = client.fetch_timetable(roll, pwd)

    if save_creds and vault.unlocked:
        save_samarth_credentials(vault, roll, pwd)

    facts, chunks = timetable_to_facts_and_chunks(report)
    snapshot_obj = {
        "roll_number": report.roll_number,
        "semester_label": report.semester_label,
        "fetched_at": report.fetched_at,
        "weekly_slots": len(report.weekly_slots),
        "events": len(report.events),
    }
    html_path = _store_samarth_snapshot(
        db,
        vault,
        data_dir,
        title=SAMARTH_TIMETABLE_DOC_TITLE,
        roll=roll,
        snapshot_obj=snapshot_obj,
        facts=facts,
        chunks=chunks,
        export_prefix="dcrust_timetable",
        html_body=format_timetable_html(report),
    )
    db.audit("timetable", f"samarth sync roll={roll} slots={len(report.weekly_slots)} events={len(report.events)}")
    return report, html_path
