"""DCRUST syllabus PDF/DOCX course parser, unit extractor, and formal table formatter."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from pypdf.errors import PdfReadError

from smriti.ingest.parsers import SUPPORTED as PARSER_SUPPORTED
from smriti.ingest.parsers import parse as parse_document
from smriti.university.pyq import normalize_course_code
from smriti.university.pyq_analyzer import _md_cell, extract_unit_filter
from smriti.university.syllabus import (
    SyllabusCatalog,
    SyllabusEntry,
    extract_syllabus_filters,
    load_syllabus_catalog,
)

_UNIT_ROMAN = {1: "Unit I", 2: "Unit II", 3: "Unit III", 4: "Unit IV", 5: "Unit V"}
_UNIT_VAL = {"i": 1, "1": 1, "ii": 2, "2": 2, "iii": 3, "3": 3, "iv": 4, "4": 4, "v": 5, "5": 5}

_COURSE_CODE_TOKEN_RE = re.compile(r"\b([A-Za-z]{2,8}[\s\-]*\d{2,4}[A-Za-z]{0,3})\b")
_COURSE_CODE_LINE_RE = re.compile(
    r"^\s*Course\s+Code\s*[:\-]\s*([A-Za-z0-9\-/]{3,20})\b",
    re.IGNORECASE,
)
_COURSE_TITLE_LINE_RE = re.compile(
    r"^\s*(?:Title\s+of\s+the\s+Course|Course\s+Title|Subject\s+Title)\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)
_OLD_COURSE_HEADER_RE = re.compile(
    r"^\s*([A-Z]{2,8}(?:[\s\-]+\d{2,4}[\s\-]*[A-Z]{0,3}|\d{2,4}[A-Z]{0,3}))\s+([A-Z][A-Za-z0-9\s,&/().:'\-]{2,95})$"
)
_UNIT_HEADER_RE = re.compile(
    r"^\s*Unit\s*[-–—:]?\s*(IV|III|II|I|V|[1-5])\b(?:\s*\([^)]*\))?\s*(?:[:.\-–—]+\s*(.*))?$",
    re.IGNORECASE,
)
_SECTION_END_RE = re.compile(
    r"^\s*(?:Text\s*Books?|Reference\s*Books?|Suggested\s*Books?|Course\s*Outcomes?|Outcome\s*\(CO\)|"
    r"List\s+of\s+Experiments|Note\s*:)\b",
    re.IGNORECASE,
)
_SEMESTER_RE = re.compile(
    r"\b(?:Semester\s*[-–—:]?\s*([IVX]{1,4}|\d{1,2})|([IVX]{1,4}|\d{1,2})\s*(?:st|nd|rd|th)?\s*Semester)\b",
    re.IGNORECASE,
)
_LTP_INLINE_RE = re.compile(r"\bL\s*[- ]\s*T\s*[- ]\s*P\s*[:\-]?\s*([0-9]+\s*[- ]\s*[0-9]+\s*[- ]\s*[0-9]+)", re.IGNORECASE)
_CREDITS_INLINE_RE = re.compile(r"\bCredits?\s*[:\-]\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE)
_SCHEME_HEADER_SEM_RE = re.compile(r"\bSEMESTER\s*[-–—:]?\s*([IVX]{1,4}|\d{1,2})\b", re.IGNORECASE)
_SCHEME_ROW_RE = re.compile(
    r"^\s*(?:\d{1,2}\.?\s+)?([A-Z]{2,8}(?:[\s\-]*\d{2,4}[\s\-]*[A-Z]{0,3}))\s+([A-Za-z][A-Za-z0-9\s,&/().:'\-]{3,90}?)"
    r"(?:\s+((?:[0-8]|-)(?:\s+(?:[0-8]|-)){1,2})\s+(?:\d+|-)(?:\s+(?:\d+|-)){1,3}\s+(\d+(?:\.\d+)?)\s+\d+)?\s*$"
)
_TRAILING_MARKS_RE = re.compile(r"\s+(?:[0-8]|-)(?:\s+(?:\d{1,3}|-)){3,}$")
_SUMMARY_INTENT_RE = re.compile(
    r"\b(?:summari[sz]e|summary|overview|contents?\s+of|subjects?\s+(?:and\s+syllabus\s+)?in|"
    r"list\s+(?:all\s+)?subjects|courses?\s+in)\b",
    re.IGNORECASE,
)
_NON_SUBJECT_NOISE_RE = re.compile(
    r"\b(?:dcrust|university|official|latest|complete|full|new|old|scheme|and|syllabi|syllabus|"
    r"show|give|get|find|list|fetch|download|send|open|check|search|tell|me|my|what|which|is|are|"
    r"the|of|for|in|on|from|about|please|all|available|summarize|summarise|summary|subjects?|courses?|"
    r"topics?|units?|chapters?|branch|year|yr|sem|semester|1st|2nd|3rd|4th|first|second|third|fourth|"
    r"b\.?\s*tech|btech|m\.?\s*tech|mtech|bca|mca|bba|mba|b\.?\s*arch|barch|cse|it|ece|eee|ee|mech|mechanical|civil|biotech)\b",
    re.IGNORECASE,
)
_PREFIX_BRANCH_MAP = {
    "CSE": "cse_it", "IT": "cse_it", "PCCSE": "cse_it", "ESCSE": "cse_it", "GPCSE": "cse_it",
    "ECE": "ece", "PCECE": "ece", "ESECE": "ece",
    "EE": "ee_eee", "EEE": "ee_eee", "ESEE": "ee_eee",
    "ME": "mech_aero", "AER": "mech_aero", "AE": "mech_aero",
    "CE": "civil",
    "BT": "bio_chem", "CHE": "bio_chem",
}
_STOPWORDS = frozenset({"of", "and", "in", "for", "to", "the", "a", "an", "with", "on", "by", "or"})

_SYLLABUS_CACHE: dict[tuple[str, int], ParsedSyllabusDoc] = {}
_CACHE_LOCK = threading.Lock()


@dataclass
class CourseSyllabus:
    """Structured course syllabus extracted from a DCRUST scheme/syllabus document."""

    course_code: str
    course_title: str
    semester: str = ""
    ltp: str = ""
    credits: str = ""
    units: dict[int, str] = field(default_factory=dict)
    text_books: list[str] = field(default_factory=list)
    page_start: int = 1
    page_end: int = 1


@dataclass
class ParsedSyllabusDoc:
    """Cached parsed courses and scheme rows for a single syllabus PDF/DOCX."""

    courses: list[CourseSyllabus] = field(default_factory=list)
    scheme_rows: list[CourseSyllabus] = field(default_factory=list)


@dataclass
class SyllabusAnalysisResult:
    """Formal Markdown table response for a subject, unit, or syllabus document summary."""

    markdown: str
    citations: list[str]
    attachments: list[str]
    subject_title: str
    source_title: str
    units_matched: int


def _clean_course_title(raw: str) -> str:
    txt = " ".join(raw.split()).strip(" :-|")
    # Strip trailing evaluation-scheme numbers glued on same line (e.g. "Compiler Design 15")
    txt = re.sub(r"\s+(?:\d{1,3}|-)\s*$", "", txt).strip()
    txt = re.sub(r"\s+(?:Minor|TCA|TES|PCA|PES|Total)\b.*$", "", txt, flags=re.IGNORECASE).strip()
    return txt


def _clean_code(raw: str) -> str:
    return re.sub(r"\s+", "", raw).strip().upper()


def _extract_course_metadata(lines: list[str]) -> tuple[str, str, str]:
    joined = " ".join(lines[:10])
    sem = ""
    if m_sem := _SEMESTER_RE.search(joined):
        sem = (m_sem.group(1) or m_sem.group(2) or "").upper()
    ltp = ""
    if m_ltp := _LTP_INLINE_RE.search(joined):
        ltp = re.sub(r"\s+", "-", m_ltp.group(1).strip())
    credits = ""
    if m_cr := _CREDITS_INLINE_RE.search(joined):
        credits = m_cr.group(1)
    return sem, ltp, credits


def _parse_docx_table_cell_header(line: str) -> tuple[str, str] | None:
    clean = " ".join(line.replace("|", " ").split()).strip()
    if m := _OLD_COURSE_HEADER_RE.match(clean):
        code = _clean_code(m.group(1))
        title = _clean_course_title(m.group(2))
        if any(ch.isdigit() for ch in code) and len(title) >= 3 and not title.upper().startswith(("SEMESTER", "YEAR")):
            return code, title
    return None


def parse_syllabus_document(pages: list[tuple[int, str]]) -> ParsedSyllabusDoc:
    """Parse DCRUST syllabus pages into structured course blocks and scheme summary rows."""
    lines_stream: list[tuple[int, str]] = []
    for pg, txt in pages:
        for raw_line in txt.splitlines():
            line = " ".join(raw_line.split()).strip()
            if line:
                lines_stream.append((pg, line))

    # 1. Collect scheme summary rows from scheme-of-studies pages
    scheme_rows: list[CourseSyllabus] = []
    seen_scheme: set[tuple[str, str]] = set()
    scheme_line_indices: set[int] = set()
    cur_scheme_sem = ""
    cur_scheme_pg = -1
    in_scheme_table = False
    for idx, (pg, line) in enumerate(lines_stream):
        if "SCHEME OF STUDIES" in line.upper() or "COURSE TITLE" in line.upper():
            in_scheme_table = True
            cur_scheme_pg = pg
            scheme_line_indices.add(idx)
            if m_sem := _SCHEME_HEADER_SEM_RE.search(line):
                cur_scheme_sem = m_sem.group(1).upper()
            continue
        if in_scheme_table:
            if (
                (pg != cur_scheme_pg and not _SCHEME_HEADER_SEM_RE.search(line) and "COURSE" not in line.upper())
                or _UNIT_HEADER_RE.match(line)
                or _COURSE_CODE_LINE_RE.match(line)
            ):
                in_scheme_table = False
            else:
                cur_scheme_pg = pg
                scheme_line_indices.add(idx)
                if m_sem := _SCHEME_HEADER_SEM_RE.search(line):
                    cur_scheme_sem = m_sem.group(1).upper()
                if line.upper().startswith("TOTAL"):
                    in_scheme_table = False
                    continue
                clean_row = line.replace(" | ", " ")
                if m_row := _SCHEME_ROW_RE.match(clean_row):
                    code = _clean_code(m_row.group(1))
                    title = _clean_course_title(_TRAILING_MARKS_RE.sub("", m_row.group(2)))
                    if (
                        any(ch.isdigit() for ch in code)
                        and len(title) >= 3
                        and not title.upper().startswith(("SEMESTER", "YEAR", "CREDIT", "SCHEME"))
                    ):
                        key = (cur_scheme_sem, normalize_course_code(code))
                        if key not in seen_scheme:
                            seen_scheme.add(key)
                            ltp_raw, cr_v = m_row.group(3), m_row.group(4)
                            ltp_parts = ["0" if tok == "-" else tok for tok in (ltp_raw or "").split()]
                            if len(ltp_parts) == 2:
                                ltp_parts.append("0")
                            ltp = "-".join(ltp_parts) if len(ltp_parts) == 3 else ""
                            scheme_rows.append(
                                CourseSyllabus(
                                    course_code=code,
                                    course_title=title,
                                    semester=cur_scheme_sem,
                                    ltp=ltp,
                                    credits=cr_v or "",
                                    page_start=pg,
                                    page_end=pg,
                                )
                            )
                continue

    # 2. Extract detailed course syllabus blocks (Course Code / Title / Units)
    courses: list[CourseSyllabus] = []
    cur: CourseSyllabus | None = None
    cur_header_lines: list[str] = []
    cur_unit: int | None = None
    unit_buf: dict[int, list[str]] = {}
    in_books = False
    books_buf: list[str] = []
    pending_code = ""

    def _finalize_course() -> None:
        nonlocal cur, cur_header_lines, cur_unit, unit_buf, in_books, books_buf
        if cur is None:
            return
        if cur.units or unit_buf:
            for u_num, buf in unit_buf.items():
                txt = " ".join(buf).strip()
                if txt:
                    cur.units[u_num] = txt
        if cur.units:
            sem, ltp, credits = _extract_course_metadata(cur_header_lines)
            if sem and not cur.semester:
                cur.semester = sem
            if ltp and not cur.ltp:
                cur.ltp = ltp
            if credits and not cur.credits:
                cur.credits = credits
            cur.text_books = books_buf[:4]
            courses.append(cur)
        cur = None
        cur_header_lines = []
        cur_unit = None
        unit_buf = {}
        in_books = False
        books_buf = []

    for idx, (pg, line) in enumerate(lines_stream):
        if idx in scheme_line_indices:
            continue
        if m_cc := _COURSE_CODE_LINE_RE.match(line):
            _finalize_course()
            pending_code = _clean_code(m_cc.group(1))
            cur_header_lines = [line]
            continue

        if m_tt := _COURSE_TITLE_LINE_RE.match(line):
            if cur is not None and not cur.units:
                _finalize_course()
            title = _clean_course_title(m_tt.group(1))
            cur = CourseSyllabus(
                course_code=pending_code or "COURSE",
                course_title=title,
                page_start=pg,
                page_end=pg,
            )
            cur_header_lines.append(line)
            pending_code = ""
            cur_unit = None
            unit_buf = {}
            in_books = False
            books_buf = []
            continue

        if m_old := _parse_docx_table_cell_header(line):
            code_cand, title_cand = m_old
            # Avoid starting a new course on uppercase notes inside units
            if not re.search(r"\b(?:SCHEME|EXAMINATION|MARKS|TOTAL|CREDIT|DURATION|NOTE)\b", line, re.IGNORECASE):
                _finalize_course()
                cur = CourseSyllabus(
                    course_code=code_cand,
                    course_title=title_cand,
                    page_start=pg,
                    page_end=pg,
                )
                cur_header_lines = [line]
                pending_code = ""
                cur_unit = None
                unit_buf = {}
                in_books = False
                books_buf = []
                continue

        if cur is None:
            continue

        cur.page_end = pg
        if len(cur_header_lines) < 12 and cur_unit is None:
            cur_header_lines.append(line)

        if m_unit := _UNIT_HEADER_RE.match(line):
            u_num = _UNIT_VAL.get(m_unit.group(1).lower())
            if u_num is not None:
                in_books = False
                cur_unit = u_num
                unit_buf.setdefault(cur_unit, [])
                inline_rest = (m_unit.group(2) or "").strip()
                if inline_rest:
                    unit_buf[cur_unit].append(inline_rest)
                continue

        if _SECTION_END_RE.match(line):
            cur_unit = None
            in_books = bool(re.match(r"^\s*Text\s*Books?", line, re.IGNORECASE))
            continue

        if in_books:
            if re.match(r"^\s*(?:Reference|Course\s*Outcome|Outcome|Note)\b", line, re.IGNORECASE):
                in_books = False
            elif len(books_buf) < 4 and re.match(r"^(?:\d+\.|[A-Z])", line):
                books_buf.append(line)
            continue

        if cur_unit is not None:
            unit_buf[cur_unit].append(line)

    _finalize_course()

    # Backfill semester/ltp/credits from scheme rows if missing on course blocks
    by_code = {normalize_course_code(r.course_code): r for r in scheme_rows}
    for c in courses:
        ref = by_code.get(normalize_course_code(c.course_code))
        if ref:
            if not c.semester and ref.semester:
                c.semester = ref.semester
            if not c.ltp and ref.ltp:
                c.ltp = ref.ltp
            if not c.credits and ref.credits:
                c.credits = ref.credits

    return ParsedSyllabusDoc(courses=courses, scheme_rows=scheme_rows)


def _extract_pdf_fast(doc_path: Path) -> list[tuple[int, str]]:
    """Extract PDF text layers quickly without running slow per-page OCR on cover/diagram pages."""
    from pypdf import PdfReader

    reader = PdfReader(str(doc_path))
    pages: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, 1):
        txt = (page.extract_text() or "").strip()
        if txt:
            pages.append((i, txt))
    if len(pages) >= 2:
        return pages
    # Pure scanned PDF fallback
    return parse_document(doc_path)


def _parse_entry_cached(entry: SyllabusEntry, syllabus_dir: Path) -> ParsedSyllabusDoc | None:
    if not entry.local_relpath:
        return None
    doc_path = syllabus_dir / entry.local_relpath
    if not doc_path.exists() or doc_path.suffix.lower() not in PARSER_SUPPORTED:
        return None
    try:
        mtime_ns = doc_path.stat().st_mtime_ns
    except OSError:
        return None
    key = (str(doc_path.resolve()), mtime_ns)
    with _CACHE_LOCK:
        if key in _SYLLABUS_CACHE:
            return _SYLLABUS_CACHE[key]
    try:
        pages = _extract_pdf_fast(doc_path) if doc_path.suffix.lower() == ".pdf" else parse_document(doc_path)
    except (OSError, PdfReadError, ValueError, RuntimeError):
        return None
    parsed = parse_syllabus_document(pages)
    with _CACHE_LOCK:
        _SYLLABUS_CACHE[key] = parsed
    return parsed


def _match_specific_entry(question: str, cat: SyllabusCatalog, syllabus_dir: Path) -> SyllabusEntry | None:
    q_norm = re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()
    q_toks = {t for t in q_norm.split() if len(t) >= 2 and t not in _STOPWORDS}
    best: tuple[float, SyllabusEntry] | None = None
    for e in cat.entries:
        if not e.local_relpath or not (syllabus_dir / e.local_relpath).exists():
            continue
        if Path(e.local_relpath).suffix.lower() not in PARSER_SUPPORTED:
            continue
        t_norm = re.sub(r"[^a-z0-9]+", " ", e.title.lower()).strip()
        if not t_norm:
            continue
        if t_norm in q_norm:
            score = 100.0 + len(t_norm)
        else:
            t_toks = {t for t in t_norm.split() if len(t) >= 2 and t not in _STOPWORDS}
            if len(t_toks) < 2:
                continue
            overlap = len(q_toks & t_toks) / len(t_toks)
            if overlap < 0.75:
                continue
            score = overlap * 50.0 + len(t_toks)
        if best is None or score > best[0]:
            best = (score, e)
    return best[1] if best else None


def extract_syllabus_subject_query(question: str, matched_entry: SyllabusEntry | None = None) -> str:
    """Return remaining subject keywords (or course code) after stripping syllabus/branch boilerplate."""
    cleaned = question
    if matched_entry is not None:
        title_pat = re.sub(r"[^a-z0-9]+", r"\\s+", matched_entry.title.lower()).strip()
        if title_pat:
            cleaned = re.sub(title_pat, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:(?:unit|chapter)\s*[-:]?\s*(?:iv|iii|ii|i|v|[1-5])|(?:1st|2nd|3rd|4th|first|second|third|fourth)\s+(?:unit|chapter))\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = _NON_SUBJECT_NOISE_RE.sub(" ", cleaned)
    cleaned = re.sub(r"[^A-Za-z0-9\s\-+]+", " ", cleaned)
    return " ".join(cleaned.split()).strip()


def wants_syllabus_analysis(question: str, syllabus_dir: Path) -> bool:
    """True when the user asks for a subject/unit syllabus or to summarize a specific syllabus file."""
    if not re.search(r"\b(?:syllabus|syllabi)\b", question, re.IGNORECASE):
        return False
    if re.search(r"\b(?:pyqs?|pqps?|previous\s+year|past\s+papers?)\b", question, re.IGNORECASE):
        return False
    cat = load_syllabus_catalog(syllabus_dir)
    if cat is None:
        return False
    if extract_unit_filter(question) is not None or _SUMMARY_INTENT_RE.search(question):
        return True
    if _COURSE_CODE_TOKEN_RE.search(question):
        return True
    matched_entry = _match_specific_entry(question, cat, syllabus_dir)
    if matched_entry is not None:
        return True
    subj = extract_syllabus_subject_query(question)
    return len(subj) >= 2


def _candidate_entries(
    question: str,
    cat: SyllabusCatalog,
    syllabus_dir: Path,
    matched_entry: SyllabusEntry | None,
    code_hint: str = "",
) -> list[SyllabusEntry]:
    branch_id, year_id, degree, _kw = extract_syllabus_filters(question)
    if branch_id is None and code_hint:
        m_pre = re.match(r"^([A-Za-z]+)", code_hint.strip())
        if m_pre:
            branch_id = _PREFIX_BRANCH_MAP.get(m_pre.group(1).upper())
    cands: list[SyllabusEntry] = []
    for e in cat.entries:
        if not e.local_relpath or not (syllabus_dir / e.local_relpath).exists():
            continue
        if Path(e.local_relpath).suffix.lower() not in PARSER_SUPPORTED:
            continue
        if branch_id and e.department_id != branch_id and not (branch_id == "cse_it" and e.department_id == "common_1st"):
            continue
        if degree and e.degree != degree:
            continue
        if year_id and year_id != "complete" and year_id not in e.covered_years and e.year_id not in {year_id, "complete"}:
            continue
        cands.append(e)

    scheme_hint = ""
    if code_hint and code_hint[-1].upper() in {"B", "C", "D"}:
        scheme_hint = {"B": "Scheme-B", "C": "C-Scheme", "D": "NEP"}[code_hint[-1].upper()]

    cands.sort(
        key=lambda e: (
            1 if (matched_entry and e.local_relpath == matched_entry.local_relpath) else 0,
            1 if (scheme_hint and ((e.scheme and scheme_hint.lower() in e.scheme.lower()) or f"-{code_hint[-1].lower()}" in e.title.lower())) else 0,
            1 if (not degree and e.degree == "B.Tech") else 0,
            1 if e.year_id == "complete" else 0,
            e.session_sort,
        ),
        reverse=True,
    )
    if matched_entry and matched_entry not in cands:
        cands.insert(0, matched_entry)
    return cands[:16]


def _score_course(course: CourseSyllabus, subj_query: str, code_hint: str, wants_lab: bool) -> float:
    norm_c = normalize_course_code(course.course_code)
    if code_hint and norm_c == normalize_course_code(code_hint):
        return 100.0
    if not subj_query:
        return 0.0
    q_low = subj_query.lower()
    t_low = course.course_title.lower()
    is_lab = bool(re.search(r"\blab\b", t_low))
    if q_low == t_low:
        return 95.0 - (15.0 if is_lab and not wants_lab else 0.0)
    q_toks = [t for t in re.findall(r"[a-z0-9]{2,}", q_low) if t not in _STOPWORDS]
    t_toks = set(re.findall(r"[a-z0-9]{2,}", t_low))
    if not q_toks or not t_toks:
        return 0.0
    hits = sum(1 for t in q_toks if t in t_toks)
    if hits == 0:
        return 0.0
    cov = hits / len(q_toks)
    if cov < 0.75:
        return 0.0
    prec = hits / len(t_toks)
    score = cov * 60.0 + prec * 25.0 + (10.0 if q_low in t_low else 0.0)
    if is_lab and not wants_lab:
        score -= 20.0
    return score


def _format_document_summary(entry: SyllabusEntry, parsed: ParsedSyllabusDoc, syllabus_dir: Path) -> SyllabusAnalysisResult:
    doc_path = syllabus_dir / entry.local_relpath
    rows = parsed.courses or parsed.scheme_rows
    lines: list[str] = [
        f"### {entry.title} — Subject & Syllabus Summary",
        f"**Branch:** {entry.department_label} · **Degree:** {entry.degree} · **File:** `{doc_path.name}`\n",
    ]
    if not rows:
        lines.append("No structured subjects or units could be extracted from this document.")
        return SyllabusAnalysisResult(
            markdown="\n".join(lines),
            citations=[f"{entry.title} ({doc_path.name})"],
            attachments=[str(doc_path)],
            subject_title=entry.title,
            source_title=entry.title,
            units_matched=0,
        )

    # Merge detailed course unit counts onto scheme rows if both exist
    detailed_by_code = {normalize_course_code(c.course_code): c for c in parsed.courses}
    raw_rows = parsed.scheme_rows if len(parsed.scheme_rows) >= len(parsed.courses) else parsed.courses
    sem_order = {"I": 1, "1": 1, "II": 2, "2": 2, "III": 3, "3": 3, "IV": 4, "4": 4, "V": 5, "5": 5, "VI": 6, "6": 6, "VII": 7, "7": 7, "VIII": 8, "8": 8}
    display_rows = sorted(raw_rows, key=lambda r: (sem_order.get((r.semester or "").upper(), 99), r.page_start))

    lines.extend([
        f"Found **{len(display_rows)} subjects** in `{doc_path.name}`:\n",
        "| # | Sem | Code | Subject | L-T-P | Credits | Units | Page |",
        "| :---: | :---: | :--- | :--- | :---: | :---: | :---: | :---: |",
    ])
    for idx, r in enumerate(display_rows[:80], 1):
        det = detailed_by_code.get(normalize_course_code(r.course_code))
        units_str = f"Unit I–{['I', 'II', 'III', 'IV', 'V'][max(det.units) - 1]}" if det and det.units else ("Unit I–IV" if r.units else "Scheme")
        pg_str = f"p. {det.page_start}" if det else f"p. {r.page_start}"
        lines.append(
            f"| {idx} | {_md_cell(r.semester or '—')} | `{_md_cell(r.course_code)}` | "
            f"**{_md_cell(r.course_title)}** | {_md_cell(r.ltp or '—')} | {_md_cell(r.credits or '—')} | "
            f"{units_str} | {pg_str} |"
        )
    if len(display_rows) > 80:
        lines.append(f"\n*Showing first 80 of {len(display_rows)} subjects.*")
    lines.append(
        "\n*Tip: Ask e.g. `Tell me syllabus of <Subject Name>` or `Tell me unit 2 syllabus of <Subject Name>` for full unit-wise topics.*"
    )
    return SyllabusAnalysisResult(
        markdown="\n".join(lines),
        citations=[f"{entry.title} ({doc_path.name})"],
        attachments=[str(doc_path)],
        subject_title=entry.title,
        source_title=entry.title,
        units_matched=len(display_rows),
    )


def _format_course_syllabus(
    course: CourseSyllabus,
    entry: SyllabusEntry,
    syllabus_dir: Path,
    *,
    unit_filter: int | None,
) -> SyllabusAnalysisResult:
    doc_path = syllabus_dir / entry.local_relpath
    page_span = f"p. {course.page_start}" if course.page_start == course.page_end else f"pp. {course.page_start}–{course.page_end}"
    unit_heading = f" · {_UNIT_ROMAN.get(unit_filter, f'Unit {unit_filter}')}" if unit_filter is not None else ""
    sem_cred = " · ".join(
        part
        for part in (
            f"Semester {course.semester}" if course.semester else "",
            f"{course.credits} Credits" if course.credits else "",
            f"L-T-P: {course.ltp}" if course.ltp else "",
        )
        if part
    ) or "—"

    lines: list[str] = [
        f"### {course.course_code} — {course.course_title}{unit_heading}\n",
        "| Course Detail | Value |",
        "| :--- | :--- |",
        f"| **Course Code** | `{_md_cell(course.course_code)}` |",
        f"| **Subject** | **{_md_cell(course.course_title)}** |",
        f"| **Scheme / Source** | {_md_cell(entry.title)} (`{_md_cell(doc_path.name)}`, {page_span}) |",
        f"| **Semester / Credits** | {_md_cell(sem_cred)} |",
        "",
    ]

    if unit_filter is not None:
        selected_units = [(unit_filter, course.units[unit_filter])] if unit_filter in course.units else []
    else:
        selected_units = sorted(course.units.items())

    if selected_units:
        lines.extend([
            "| Unit | Syllabus Content |",
            "| :--- | :--- |",
        ])
        for u_num, u_txt in selected_units:
            u_lbl = _UNIT_ROMAN.get(u_num, f"Unit {u_num}")
            lines.append(f"| **{u_lbl}** | {_md_cell(u_txt)} |")
    else:
        u_lbl = _UNIT_ROMAN.get(unit_filter, f"Unit {unit_filter}") if unit_filter is not None else "Unit"
        lines.extend([
            "| Unit | Syllabus Content |",
            "| :--- | :--- |",
            f"| **{u_lbl}** | No matching {u_lbl} syllabus text found in `{_md_cell(doc_path.name)}`. |",
        ])

    if unit_filter is None and course.text_books:
        lines.extend(["", "**Text Books:**"])
        for tb in course.text_books:
            lines.append(f"- {tb}")

    return SyllabusAnalysisResult(
        markdown="\n".join(lines),
        citations=[f"{entry.title} ({doc_path.name} {page_span})"],
        attachments=[str(doc_path)],
        subject_title=f"{course.course_code} {course.course_title}",
        source_title=entry.title,
        units_matched=len(selected_units),
    )


def analyze_syllabus(question: str, syllabus_dir: Path) -> SyllabusAnalysisResult | None:
    """Resolve a subject, unit, or syllabus-document summary query directly from downloaded syllabus files."""
    cat = load_syllabus_catalog(syllabus_dir)
    if cat is None:
        return None

    unit_filter = extract_unit_filter(question)
    matched_entry = _match_specific_entry(question, cat, syllabus_dir)
    subj_query = extract_syllabus_subject_query(question, matched_entry=matched_entry)
    code_m = _COURSE_CODE_TOKEN_RE.search(subj_query or question)
    code_hint = code_m.group(1) if code_m else ""

    # 1. Document summary mode (e.g. "Summarize the subjects and syllabus in Revised B.Tech. CSE-B")
    if matched_entry is not None and (not subj_query or _SUMMARY_INTENT_RE.search(question)) and unit_filter is None and not code_hint:
        parsed = _parse_entry_cached(matched_entry, syllabus_dir)
        if parsed is not None:
            return _format_document_summary(matched_entry, parsed, syllabus_dir)

    if not subj_query and not code_hint:
        return None

    wants_lab = bool(re.search(r"\blab\b", question, re.IGNORECASE))
    cands = _candidate_entries(question, cat, syllabus_dir, matched_entry, code_hint=code_hint)
    best: tuple[float, SyllabusEntry, CourseSyllabus] | None = None
    for entry in cands:
        parsed = _parse_entry_cached(entry, syllabus_dir)
        if parsed is None:
            continue
        for course in parsed.courses:
            sc = _score_course(course, subj_query, code_hint, wants_lab)
            if sc <= 0:
                continue
            # Slightly prefer newest scheme when two documents have identical course title match
            ranked = sc + (entry.session_sort / 1_000_000.0)
            if best is None or ranked > best[0]:
                best = (ranked, entry, course)
        if best is not None and best[0] >= 95.0:
            break

    if best is None:
        return None
    _, best_entry, best_course = best
    return _format_course_syllabus(best_course, best_entry, syllabus_dir, unit_filter=unit_filter)
