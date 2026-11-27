"""DCRUST Previous Year Question Paper content parser, unit extractor, and frequency analyzer."""

from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from pypdf.errors import PdfReadError

from smriti.ingest.parsers import parse as parse_document
from smriti.university.pyq import (
    _MONTH_NUMS,
    PyqEntry,
    PyqSubjectGroup,
    search_pyqs,
)

_UNIT_MAP = {
    "i": 1, "1": 1, "1st": 1, "first": 1,
    "ii": 2, "2": 2, "2nd": 2, "second": 2,
    "iii": 3, "3": 3, "3rd": 3, "third": 3,
    "iv": 4, "4": 4, "4th": 4, "fourth": 4,
}
_ROMAN = {0: "Compulsory", 1: "Unit I", 2: "Unit II", 3: "Unit III", 4: "Unit IV"}

_UNIT_QUERY_RE = re.compile(
    r"\b(?:(?:unit|chapter)\s*[-:]?\s*(iv|iii|ii|i|[1-4])|(1st|2nd|3rd|4th|first|second|third|fourth)\s+(?:unit|chapter))\b",
    re.IGNORECASE,
)
_SESSION_QUERY_RE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"[\s,_-]*(20\d{2})\b",
    re.IGNORECASE,
)
_COURSE_CODE_RE = re.compile(r"\b([A-Za-z]{2,6}\d{2,4}[A-Za-z]{0,3})\b")
_FREQ_HINT_RE = re.compile(
    r"\b(?:most\s+(?:frequently\s+)?asked|frequent(?:ly)?|order\s+of|repeat(?:ed)?|rank(?:ed|ing)?|often)\b",
    re.IGNORECASE,
)
_ANALYSIS_NOISE_RE = re.compile(
    r"\b(?:analy[sz]e|analysis|summari[sz]e|summary|key|topics?|important|questions?|pyqs?|pqps?|"
    r"previous\s+year|past\s+papers?|unit|most|frequently|frequent|asked|order|repeat(?:ed)?|"
    r"from|in|of|for|the|and|give|me|all|show|tell|list|what|which|are|is|were|was|paper|"
    r"pattern|weightage|trend|breakdown|with|using)\b",
    re.IGNORECASE,
)

_UNIT_LINE_RE = re.compile(
    r"^\s*Unit\s*[-:—]?\s*([A-Za-z0-9]{1,5})\.?(?:\s*[:\-]|\s+\[?\(?\d+\s*(?:marks?)?\)?\]?)?\s*$",
    re.IGNORECASE,
)
_OCR_UNIT_ALIASES: dict[str, int] = {
    "i": 1, "1": 1, "l": 1,
    "ii": 2, "2": 2, "ll": 2, "it": 2, "ii.": 2,
    "iii": 3, "3": 3, "ot": 3, "oi": 3, "hi": 3, "ill": 3, "m": 3, "ut": 3, "oii": 3, "iu": 3,
    "iv": 4, "4": 4, "w": 4, "jv": 4, "lv": 4,
}
_BOILERPLATE_RE = re.compile(
    r"^(?:"
    r"no\.?\s*of\s*printed\s*pages|"
    r"roll\s*no\.?|"
    r"b\.?\s*tech\.?\s*examination|"
    r"\((?:first|second|third|fourth|fifth|sixth|seventh|eighth)\s+semester\)|"
    r"\([A-Z]-?\s*scheme\)|"
    r"\(re-?appear|\(main|"
    r"time\s*:\s*\d+|"
    r"\[?\s*maximum\s+marks|"
    r"before\s+answering|"
    r"should\s+ensure|"
    r"no\s+complaint|"
    r"regard,\s*will\s+be\s+entertained|"
    r"note\s*:|"
    r"attempt\s+(?:any\s+|total\s+)?five|"
    r"carry\s+equal\s+marks|"
    r"compulsory\.\s*attempt|"
    r"question\s+carries\s+equal|"
    r"\(?[0-9G-]+\)?\s*M-[A-Z0-9]+|"
    r"M-[A-Z0-9]+\s+\d+|"
    r"\d{1,3}-\d{2}/\d{1,2}\)?\s*M-[A-Z0-9]+|"
    r"\([A-Za-z0-9./-]+\)\s*M-[A-Z0-9]+|"
    r"\d{1,3}$"
    r")",
    re.IGNORECASE,
)
_INLINE_FOOTER_RE = re.compile(
    r"(?:\s*(?:\([0-9G-][^)]*\)\s*)?M-[A-Z0-9]{2,}\s*(?:\d+|P\.?T\.?O\.?)?(?:\s+\d{2,4})?|\s*P\.?T\.?O\.?\s*)$",
    re.IGNORECASE,
)
_MARKS_END_RE = re.compile(r"(?:^|\s)(15|20|12|10|8|7|6|5|4|3|2|1|7½|5×3=15)\s*$")
_SUBPART_RE = re.compile(r"^\s*(?:\(([a-e]|[ivx]{1,4})\)|[a-e]\))\s+", re.IGNORECASE)
_NUM_Q_RE = re.compile(r"^\s*(?:Q\.?\s*)?(\d{1,2})\.\s+(.+)$")

_CLUSTER_STOPWORDS = frozenset({
    "what", "do", "you", "mean", "by", "define", "explain", "discuss", "describe", "write",
    "elaborate", "list", "state", "enumerate", "briefly", "detail", "suitable", "example",
    "examples", "any", "two", "three", "four", "five", "various", "different", "ways",
    "methods", "approaches", "techniques", "context", "role", "advantages", "disadvantages",
    "objectives", "features", "can", "used", "help", "achieve", "goals", "give", "taken",
    "following", "with", "for", "and", "the", "of", "in", "to", "a", "an", "is", "are", "how",
    "some", "also", "its", "into", "towards", "promoting", "strategy", "follow", "between",
    "differentiate", "compare", "short", "notes", "about", "using", "their", "concept",
    "initiative", "initiatives", "term", "problem", "problems", "study", "case",
})

_PARSED_PAPER_CACHE: dict[tuple[str, int], list[ExtractedQuestion]] = {}
_PARSE_CACHE_LOCK = threading.Lock()


@dataclass
class ExtractedQuestion:
    unit: int  # 0 = Compulsory / Intro Q1, 1..4 = Unit I..IV
    text: str
    marks: str = ""
    session_label: str = ""
    session_sort: int = 0
    filename: str = ""
    page: int = 1


@dataclass
class QuestionCluster:
    topic_label: str
    unit: int
    questions: list[ExtractedQuestion] = field(default_factory=list)

    @property
    def session_count(self) -> int:
        return len({(q.session_label, q.filename) for q in self.questions})

    @property
    def latest_sort(self) -> int:
        return max((q.session_sort for q in self.questions), default=0)


def extract_unit_filter(question: str) -> int | None:
    m = _UNIT_QUERY_RE.search(question)
    if not m:
        return None
    tok = (m.group(1) or m.group(2) or "").lower()
    return _UNIT_MAP.get(tok)


def extract_session_filter(question: str) -> int | None:
    m = _SESSION_QUERY_RE.search(question)
    if not m:
        return None
    mon = _MONTH_NUMS.get(m.group(1).lower())
    yr = int(m.group(2))
    if mon is None:
        return None
    return yr * 100 + mon


def _clean_line(line: str) -> str:
    s = " ".join(line.split()).strip()
    if not s:
        return ""
    # Drop pure header/footer boilerplate lines
    if _BOILERPLATE_RE.match(s):
        return ""
    s = _INLINE_FOOTER_RE.sub("", s).strip()
    if not s or _BOILERPLATE_RE.match(s):
        return ""
    return s


def _resolve_unit_sequence(raw_headers: list[tuple[int, int | None]]) -> list[int]:
    """Repair OCR errors in sequential Unit I..IV headers (e.g. 'Unit OT' or repeated 'Unit I')."""
    vals = [u for _, u in raw_headers]
    if len(vals) == 4 and vals == [1, 1, 3, 4]:
        vals[1] = 2
    out: list[int] = []
    for i, v in enumerate(vals):
        if v is not None:
            # Handle duplicate Unit I right before Unit III/IV
            if i > 0 and v == 1 and out[-1] == 1:
                v = 2
            out.append(v)
        else:
            prev = out[-1] if out else 0
            nxt = next((vals[j] for j in range(i + 1, len(vals)) if vals[j] is not None), None)
            if prev in (1, 2, 3):
                out.append(prev + 1)
            elif nxt in (2, 3, 4):
                out.append(nxt - 1)
            else:
                out.append(3)
    return out


def _flush_block(lines: list[str], unit: int, entry: PyqEntry | None, page: int, out: list[ExtractedQuestion]) -> None:
    if not lines:
        return
    joined = " ".join(lines).strip()
    joined = re.sub(r"\s+", " ", joined)
    joined = re.sub(r"\s+_[ \t]+", " ", joined)
    if len(joined) < 8:
        return
    marks = ""
    m = _MARKS_END_RE.search(joined)
    if m:
        marks = m.group(1)
        joined = joined[: m.start()].strip()
    # Clean stray leading question number & inline marks before (a)/(i)
    joined = re.sub(r"^\d{1,2}\.\s*", "", joined).strip()
    joined = re.sub(r":\s*(?:15|20|10)\s+(?=\((?:a|i)\))", ": ", joined, flags=re.IGNORECASE)
    if not marks and re.search(r"\b(?:15|20)\b", joined) and "(a)" in joined:
        marks = "15"
    if len(joined) < 8:
        return
    out.append(
        ExtractedQuestion(
            unit=unit,
            text=joined,
            marks=marks,
            session_label=entry.session_label if entry else "",
            session_sort=entry.session_sort if entry else 0,
            filename=Path(entry.local_relpath).name if entry and entry.local_relpath else "",
            page=page,
        )
    )


def parse_dcrust_paper(
    pages: list[tuple[int, str]],
    *,
    entry: PyqEntry | None = None,
    course_code: str = "",
    subject_name: str = "",
) -> list[ExtractedQuestion]:
    """Parse one DCRUST question paper into unit-tagged Exam Questions."""
    stream: list[tuple[int, str, bool]] = []
    seen_body_start = False

    for page_num, raw_text in pages:
        blank_before = True
        for raw_line in raw_text.splitlines():
            if not raw_line.strip():
                blank_before = True
                continue
            cleaned = _clean_line(raw_line)
            if not cleaned:
                blank_before = True
                continue
            # Everything on page 1 before the first Unit header or numbered Q.1 / (a) is exam cover boilerplate.
            if page_num == 1 and not seen_body_start:
                if _UNIT_LINE_RE.match(cleaned) or _NUM_Q_RE.match(cleaned) or _SUBPART_RE.match(cleaned):
                    seen_body_start = True
                else:
                    continue
            if re.match(r"^(?:Note\s*:|Attempt\s+Five|Before\s+answering)", cleaned, re.IGNORECASE):
                continue
            stream.append((page_num, cleaned, blank_before))
            blank_before = False
        # Re-open body collection for subsequent pages cleanly
        if page_num >= 1:
            seen_body_start = True

    unit_positions: list[tuple[int, int | None]] = []
    for idx, (_pg, txt, _brk) in enumerate(stream):
        m = _UNIT_LINE_RE.match(txt)
        if m:
            raw_tok = m.group(1).lower().rstrip(".")
            unit_positions.append((idx, _OCR_UNIT_ALIASES.get(raw_tok)))
    resolved_units = _resolve_unit_sequence(unit_positions)
    unit_at_idx = {pos: u for (pos, _), u in zip(unit_positions, resolved_units, strict=True)}

    out: list[ExtractedQuestion] = []
    cur_unit = 0
    cur_lines: list[str] = []
    cur_page = 1
    in_subparts = False
    subpart_ended_with_marks = False

    for idx, (pg, txt, blank_before) in enumerate(stream):
        next_txt = stream[idx + 1][1] if idx + 1 < len(stream) else ""
        next_is_sub = bool(_SUBPART_RE.match(next_txt))
        next_continues_sentence = bool(next_txt and next_txt[0].islower())

        if idx in unit_at_idx:
            _flush_block(cur_lines, cur_unit, entry, cur_page, out)
            cur_lines = []
            in_subparts = False
            subpart_ended_with_marks = False
            cur_unit = unit_at_idx[idx]
            cur_page = pg
            continue

        if _NUM_Q_RE.match(txt):
            _flush_block(cur_lines, cur_unit, entry, cur_page, out)
            cur_lines = [txt]
            cur_page = pg
            in_subparts = False
            subpart_ended_with_marks = False
            if _MARKS_END_RE.search(txt) and not next_is_sub and not next_continues_sentence:
                m_val = _MARKS_END_RE.search(txt).group(1)
                if m_val in {"15", "20", "12"} and len(txt) > 25:
                    _flush_block(cur_lines, cur_unit, entry, cur_page, out)
                    cur_lines = []
            continue

        is_sub = bool(_SUBPART_RE.match(txt))
        if in_subparts and not is_sub and (subpart_ended_with_marks or blank_before):
            _flush_block(cur_lines, cur_unit, entry, cur_page, out)
            cur_lines = []
            in_subparts = False
            subpart_ended_with_marks = False

        if not cur_lines:
            cur_page = pg
        if is_sub:
            in_subparts = True
            subpart_ended_with_marks = False

        cur_lines.append(txt)
        m_end = _MARKS_END_RE.search(txt)
        if m_end and not next_is_sub and not next_continues_sentence:
            mark_val = m_end.group(1)
            if in_subparts:
                subpart_ended_with_marks = True
                if mark_val in {"15", "20"} and len(cur_lines) > 2:
                    _flush_block(cur_lines, cur_unit, entry, cur_page, out)
                    cur_lines = []
                    in_subparts = False
                    subpart_ended_with_marks = False
            elif mark_val in {"15", "20", "12"}:
                _flush_block(cur_lines, cur_unit, entry, cur_page, out)
                cur_lines = []
                in_subparts = False
                subpart_ended_with_marks = False

    _flush_block(cur_lines, cur_unit, entry, cur_page, out)
    return out


def _topic_tokens(text: str, extra_stop: set[str]) -> set[str]:
    words = re.findall(r"[a-z]{3,}", text.lower())
    out = set()
    for w in words:
        if w in _CLUSTER_STOPWORDS or w in extra_stop:
            continue
        stem = w[:-1] if len(w) > 5 and w.endswith("s") and not w.endswith("ss") else w
        out.add(stem)
    return out


def _pretty_topic_label(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    clean = re.sub(
        r"^(?:Discuss|Describe|Explain|Write and (?:briefly )?(?:explain|describe)|"
        r"List(?:\s+the)?(?:\s+any\s+\w+)?|How|What do you mean by|What is|Define)"
        r"(?:\s+the\s+following\s*:?|\s+the\s+concept\s+of|\s+various|\s+different)?\s*",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip(" :?.")
    clean = re.sub(r"^(?:the|an?)\s+", "", clean, flags=re.IGNORECASE)
    if len(clean) > 78:
        cut = clean.rfind(" ", 0, 78)
        clean = clean[: cut if cut > 20 else 78].rstrip(" ,:") + "…"
    return clean[:1].upper() + clean[1:] if clean else text[:78]


def cluster_pyq_questions(
    questions: list[ExtractedQuestion],
    *,
    subject_name: str = "",
) -> list[QuestionCluster]:
    """Group similar/repeated exam questions across papers and sort by frequency desc."""
    extra_stop = set(re.findall(r"[a-z]{3,}", subject_name.lower()))
    clusters: list[tuple[set[str], QuestionCluster]] = []

    ordered = sorted(questions, key=lambda q: (-q.session_sort, q.unit))
    for q in ordered:
        toks = _topic_tokens(q.text, extra_stop)
        best_idx = -1
        best_score = 0.0
        for idx, (seed_toks, clus) in enumerate(clusters):
            if clus.unit != q.unit or not toks or not seed_toks:
                continue
            inter = len(toks & seed_toks)
            if inter == 0:
                continue
            contain = inter / min(len(toks), len(seed_toks))
            jaccard = inter / len(toks | seed_toks)
            score = max(contain * 0.85, jaccard)
            if (contain >= 0.50 or jaccard >= 0.42) and score > best_score:
                best_score = score
                best_idx = idx
        if best_idx != -1:
            clusters[best_idx][1].questions.append(q)
        else:
            clusters.append(
                (toks, QuestionCluster(topic_label=_pretty_topic_label(q.text), unit=q.unit, questions=[q]))
            )

    result = [c for _, c in clusters]
    result.sort(key=lambda c: (-c.session_count, -len(c.questions), -c.latest_sort))
    return result


def _resolve_subject_group(question: str, pyq_dir: Path) -> PyqSubjectGroup | None:
    code_match = _COURSE_CODE_RE.search(question)
    if code_match:
        res = search_pyqs(code_match.group(1), pyq_dir, max_subjects=3)
        if res.matches:
            return res.matches[0]

    cleaned = _UNIT_QUERY_RE.sub(" ", question)
    cleaned = _SESSION_QUERY_RE.sub(" ", cleaned)
    cleaned = _ANALYSIS_NOISE_RE.sub(" ", cleaned)
    cleaned = " ".join(cleaned.split()).strip()
    if cleaned:
        res = search_pyqs(cleaned, pyq_dir, max_subjects=3)
        if res.matches:
            return res.matches[0]
    res = search_pyqs(question, pyq_dir, max_subjects=3)
    return res.matches[0] if res.matches else None


@dataclass
class PyqAnalysisResult:
    markdown: str
    citations: list[str]
    attachments: list[str]
    subject_code: str
    subject_name: str
    papers_analyzed: int
    questions_extracted: int


def _parse_entry_cached(
    entry: PyqEntry,
    pyq_dir: Path,
    course_code: str,
    subject_name: str,
) -> tuple[PyqEntry, list[ExtractedQuestion]]:
    pdf_path = pyq_dir / entry.local_relpath
    try:
        mtime_ns = pdf_path.stat().st_mtime_ns
    except OSError:
        return entry, []
    key = (str(pdf_path.resolve()), mtime_ns)
    with _PARSE_CACHE_LOCK:
        if key in _PARSED_PAPER_CACHE:
            return entry, _PARSED_PAPER_CACHE[key]
    try:
        pages = parse_document(pdf_path)
    except (OSError, PdfReadError, ValueError, RuntimeError):
        return entry, []
    qs = parse_dcrust_paper(pages, entry=entry, course_code=course_code, subject_name=subject_name)
    with _PARSE_CACHE_LOCK:
        _PARSED_PAPER_CACHE[key] = qs
    return entry, qs


def _md_cell(text: str) -> str:
    """Sanitize a string for single-line GFM Markdown table cells."""
    return " ".join(text.split()).replace("|", "\\|")


def analyze_subject_pyqs(question: str, pyq_dir: Path) -> PyqAnalysisResult | None:
    """Analyze downloaded PYQ PDFs for a subject (unit-wise frequency ranking or session summary)."""
    grp = _resolve_subject_group(question, pyq_dir)
    if grp is None:
        return None

    unit_filter = extract_unit_filter(question)
    session_filter = extract_session_filter(question)

    all_entries = [
        e for e in grp.entries if e.local_relpath and (pyq_dir / e.local_relpath).exists()
    ]
    if not all_entries:
        return None

    target_entries = all_entries
    if session_filter is not None:
        filtered = [e for e in all_entries if e.session_sort == session_filter]
        if not filtered:
            return None
        target_entries = filtered

    # Parse all downloaded papers for the subject concurrently & cache by (path, mtime)
    parsed_by_file: dict[str, tuple[PyqEntry, list[ExtractedQuestion]]] = {}
    all_questions: list[ExtractedQuestion] = []
    with ThreadPoolExecutor(max_workers=min(4, len(all_entries))) as pool:
        futs = [
            pool.submit(_parse_entry_cached, entry, pyq_dir, grp.course_code, grp.subject_name)
            for entry in all_entries
        ]
        for fut in futs:
            entry, qs = fut.result()
            if qs:
                parsed_by_file[entry.local_relpath] = (entry, qs)
                all_questions.extend(qs)

    if not all_questions:
        return None

    # Build cross-paper clusters so even single-session summaries can highlight repeated topics
    full_clusters = cluster_pyq_questions(all_questions, subject_name=grp.subject_name)
    freq_by_qtext: dict[tuple[str, str], int] = {}
    for clus in full_clusters:
        for q in clus.questions:
            freq_by_qtext[(q.filename, q.text)] = clus.session_count

    attachments = [str(pyq_dir / e.local_relpath) for e in target_entries]
    citations = [
        f"{Path(e.local_relpath).name} ({e.session_label})"
        for e in target_entries
        if e.local_relpath in parsed_by_file
    ]

    # Mode A: Single Exam Session Summary (e.g., "Summarize the key topics and important questions from CSE423C ... June 2024")
    if session_filter is not None and len(target_entries) <= 2:
        lines: list[str] = []
        target_qs: list[ExtractedQuestion] = []
        for entry in target_entries:
            _, pqs = parsed_by_file.get(entry.local_relpath, (entry, []))
            if unit_filter is not None:
                pqs = [q for q in pqs if q.unit == unit_filter]
            target_qs.extend(pqs)
            unit_heading = f" · {_ROMAN.get(unit_filter, f'Unit {unit_filter}')}" if unit_filter is not None else ""
            lines.append(
                f"### {grp.course_code} — {grp.subject_name} ({entry.session_label}){unit_heading}\n"
            )
            repeated = [
                (q, freq_by_qtext.get((q.filename, q.text), 1))
                for q in pqs
                if freq_by_qtext.get((q.filename, q.text), 1) > 1
            ]
            if repeated:
                lines.append("**Key Recurring Topics Across Papers:**\n")
                lines.append("| Unit | Topic | Frequency |")
                lines.append("| :--- | :--- | :---: |")
                for q, cnt in sorted(repeated, key=lambda x: -x[1]):
                    u_lbl = _ROMAN.get(q.unit, f"Unit {q.unit}")
                    lines.append(
                        f"| {u_lbl} | **{_md_cell(_pretty_topic_label(q.text))}** | **{cnt}×** ({cnt}/{len(all_entries)}) |"
                    )
                lines.append("")

            lines.append("**Questions Asked in This Paper:**\n")
            lines.append("| Unit | Question | Marks | Freq |")
            lines.append("| :--- | :--- | :---: | :---: |")
            for q in sorted(pqs, key=lambda item: item.unit):
                u_lbl = _ROMAN.get(q.unit, f"Unit {q.unit}")
                marks_val = q.marks or "—"
                freq = freq_by_qtext.get((q.filename, q.text), 1)
                freq_val = f"**{freq}×**" if freq > 1 else "1×"
                lines.append(f"| {u_lbl} | {_md_cell(q.text)} | {marks_val} | {freq_val} |")
            lines.append("")
        return PyqAnalysisResult(
            markdown="\n".join(lines).strip(),
            citations=citations,
            attachments=attachments[:12],
            subject_code=grp.course_code,
            subject_name=grp.subject_name,
            papers_analyzed=len(target_entries),
            questions_extracted=len(target_qs),
        )

    # Mode B: Cross-Paper Unit / Full-Subject Frequency Analysis
    target_questions: list[ExtractedQuestion] = [
        q
        for entry in target_entries
        for q in parsed_by_file.get(entry.local_relpath, (entry, []))[1]
    ]
    scoped_qs = (
        [q for q in target_questions if q.unit == unit_filter]
        if unit_filter is not None
        else list(target_questions)
    )
    if not scoped_qs:
        return None
    scoped_clusters = cluster_pyq_questions(scoped_qs, subject_name=grp.subject_name)
    unit_label = _ROMAN.get(unit_filter, "All Units") if unit_filter is not None else "All Units"
    sessions_span = ", ".join(e.session_label for e in target_entries)
    analyzed_count = sum(1 for e in target_entries if e.local_relpath in parsed_by_file)

    out_lines: list[str] = [
        f"### {grp.course_code} — {grp.subject_name} · {unit_label} PYQ Analysis",
        f"Analyzed **{analyzed_count} question papers** ({sessions_span}) — **{len(scoped_qs)} questions** ({unit_label}) ranked by frequency:\n",
    ]
    if unit_filter is None:
        out_lines.append("| # | Unit | Topic | Frequency | Sessions |")
        out_lines.append("| :---: | :--- | :--- | :---: | :--- |")
    else:
        out_lines.append("| # | Topic | Frequency | Sessions |")
        out_lines.append("| :---: | :--- | :---: | :--- |")

    for rank, clus in enumerate(scoped_clusters, 1):
        cnt = clus.session_count
        freq_word = "time" if cnt == 1 else "times"
        sessions = ", ".join(dict.fromkeys(q.session_label for q in clus.questions))
        if unit_filter is None:
            u_lbl = _ROMAN.get(clus.unit, f"Unit {clus.unit}")
            out_lines.append(
                f"| {rank} | {u_lbl} | **{_md_cell(clus.topic_label)}** | **{cnt} {freq_word}** ({cnt}/{analyzed_count}) | {_md_cell(sessions)} |"
            )
        else:
            out_lines.append(
                f"| {rank} | **{_md_cell(clus.topic_label)}** | **{cnt} {freq_word}** ({cnt}/{analyzed_count}) | {_md_cell(sessions)} |"
            )

    out_lines.extend(["", f"**All {unit_label} Questions (ordered by frequency):**\n"])
    if unit_filter is None:
        out_lines.append("| # | Freq | Unit | Session | Question | Marks |")
        out_lines.append("| :---: | :---: | :--- | :--- | :--- | :---: |")
    else:
        out_lines.append("| # | Freq | Session | Question | Marks |")
        out_lines.append("| :---: | :---: | :--- | :--- | :---: |")

    for rank, clus in enumerate(scoped_clusters, 1):
        cnt = clus.session_count
        for q in clus.questions:
            marks_val = q.marks or "—"
            if unit_filter is None:
                u_lbl = _ROMAN.get(q.unit, f"Unit {q.unit}")
                out_lines.append(
                    f"| {rank} | **{cnt}×** | {u_lbl} | {_md_cell(q.session_label)} | {_md_cell(q.text)} | {marks_val} |"
                )
            else:
                out_lines.append(
                    f"| {rank} | **{cnt}×** | {_md_cell(q.session_label)} | {_md_cell(q.text)} | {marks_val} |"
                )

    return PyqAnalysisResult(
        markdown="\n".join(out_lines),
        citations=citations,
        attachments=attachments[:12],
        subject_code=grp.course_code,
        subject_name=grp.subject_name,
        papers_analyzed=analyzed_count,
        questions_extracted=len(scoped_qs),
    )
