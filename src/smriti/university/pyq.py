"""DCRUST EDP (dcrustedp.in) Previous Year Question Paper catalog, downloader, sorter, and search."""

from __future__ import annotations

import datetime as dt
import html as html_lib
import http.cookiejar
import json
import os
import re
import ssl
import string
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    _IST: dt.tzinfo = ZoneInfo("Asia/Kolkata")
except ZoneInfoNotFoundError:
    _IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")
_APPROVED_PYQ_HOSTS = {"dcrustedp.in", "www.dcrustedp.in"}


class _SafeHostRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: set[str]):
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        host = (parsed.hostname or "").lower()
        if parsed.scheme.lower() not in {"http", "https"} or host not in self.allowed_hosts:
            raise urllib.error.URLError(f"Blocked redirect to untrusted host: {host or newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

DCRUSTEDP_BASE_URL = "https://www.dcrustedp.in"
DCRUSTEDP_INDEX_PATH = "/dcrustpqp.php"
DCRUSTEDP_SESSION_PATH = "/dcrustpqp2.php"
DCRUSTEDP_LETTER_PATH = "/pqp.php"

_EXAM_RE = re.compile(
    r"dcrustpqp2\.php\?examid=(\d+)['\"][^>]*>([^<]+)<",
    re.IGNORECASE,
)
# Handles unclosed onclick quotes on dcrustedp.in rows like:
# <a href='dcrustpqp/dec2024/CCDMS1101C.pdf' onclick='return popitup('dcrustpqp/dec2024/CCDMS1101C.pdf')>CCDMS1101C</a></td><td>NAME</td>
_ROW_RE = re.compile(
    r"<a\s+href=['\"]([^'\"]+\.pdf)['\"][^>]*>\s*([^<]+?)\s*</a>\s*</td>\s*<td>\s*([^<]*?)\s*(?:</td>|<tr>|$)",
    re.IGNORECASE | re.DOTALL,
)
_DIRECT_PDF_RE = re.compile(
    r"<a\s+href=['\"]([^'\"]+\.pdf)['\"][^>]*>\s*([^<]+?)\s*</a>",
    re.IGNORECASE,
)

_MONTH_NUMS: dict[str, int] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_PYQ_BOILERPLATE = re.compile(
    r"\b(?:previous\s+years?|last\s+\d+\s+years?|question\s+papers?|past\s+papers?|"
    r"pyqs?|pqps?|dcrustedp|dcrust|papers?|question|questions|subject|course|code|name|"
    r"all|available|show|give|get|find|list|fetch|download|open|send|check|search|"
    r"please|for|of|the|me|my|in|on|with|and|from|to|any|old|recent|latest)\b",
    re.IGNORECASE,
)
_COURSE_CODE_RE = re.compile(r"\b([A-Za-z]{1,6}[-_\s]?\d{2,4}[A-Za-z]{0,4})\b")
_STOP_TOKENS = frozenset({"and", "of", "the", "in", "for", "to", "a", "an", "with", "on", "by"})

ABBREVIATION_ALIASES: dict[str, str] = {
    "dbms": "data base management system",
    "dsa": "data structures and algorithms",
    "os": "operating system",
    "coa": "computer organization architecture",
    "cn": "computer networks",
    "flat": "formal languages automata theory",
    "toc": "formal languages automata theory",
    "ai": "artificial intelligence",
    "ml": "machine learning",
    "oop": "object oriented programming",
    "oops": "object oriented programming",
    "se": "software engineering",
    "cd": "compiler design",
    "cg": "computer graphics",
    "daa": "design analysis algorithms",
    "sdec": "software design enterprise computing",
    "sc": "soft computing",
    "gc": "green computing",
    "pts": "professional training seminar",
}

_CATALOG_CACHE: dict[Path, tuple[float, PyqCatalog]] = {}
_CACHE_LOCK = threading.Lock()


@dataclass
class PyqEntry:
    """Single question paper row scraped from dcrustedp.in."""

    exam_id: str
    session_label: str
    session_slug: str
    session_sort: int  # YYYYMM e.g. 202412
    raw_code: str
    course_code: str
    subject_name: str
    remote_path: str
    remote_url: str
    local_relpath: str = ""
    status: str = "pending"  # pending | downloaded | missing_remote | invalid | error
    size_bytes: int = 0


@dataclass
class PyqCatalog:
    """Complete catalog loaded from or saved to pyqs/index.json."""

    source_url: str
    updated_at: str
    entries: list[PyqEntry] = field(default_factory=list)
    exam_sessions: list[dict[str, str]] = field(default_factory=list)


@dataclass
class PyqSubjectGroup:
    """Matched subject and all its past papers ordered newest-first."""

    course_code: str
    subject_name: str
    score: float
    entries: list[PyqEntry] = field(default_factory=list)


@dataclass
class PyqSearchResult:
    """Search response for a subject code or subject name query."""

    raw_query: str
    cleaned_query: str
    matches: list[PyqSubjectGroup] = field(default_factory=list)
    total_papers: int = 0
    catalog_total_entries: int = 0
    catalog_ready: bool = True


def _sanitize_fs_part(text: str, max_len: int = 72) -> str:
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", text or "")
    clean = re.sub(r"\s+", " ", clean).strip(" .-_")
    if len(clean) > max_len:
        clean = clean[:max_len].rstrip(" .-_")
    return clean or "UNKNOWN"


def normalize_course_code(raw: str) -> str:
    """Normalize codes like 'cse-302c' or 'cse201C' -> 'CSE302C'."""
    return re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()


def _normalize_subject_name(name: str) -> str:
    txt = html_lib.unescape(name or "").strip()
    txt = re.sub(r"\s+", " ", txt)
    return txt


def _search_tokens(text: str) -> list[str]:
    norm = html_lib.unescape(text or "").lower()
    norm = norm.replace("&", " and ")
    norm = re.sub(r"\bdatabase\b", "data base", norm)
    norm = re.sub(r"\bdatabases\b", "data bases", norm)
    norm = re.sub(r"[^a-z0-9]+", " ", norm)
    toks = [t for t in norm.split() if t and t not in _STOP_TOKENS]
    out: list[str] = []
    for t in toks:
        if t.endswith("s") and len(t) > 4:
            out.append(t[:-1])
        else:
            out.append(t)
    return out


def parse_session_sort(session_label: str, remote_path: str = "") -> tuple[int, str, str]:
    """Return (YYYYMM_sort_int, YYYY-MM_prefix, display_label) from session strings."""
    raw = re.sub(r"\s+", " ", (session_label or "").strip())
    is_phd = "ph.d" in raw.lower() or "phd" in raw.lower() or "phd" in remote_path.lower()
    m = re.search(
        r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"[\s,.-]*(\d{4})",
        raw,
        re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r"(jan|feb|mar|apr|may|june?|july?|aug|sep|oct|nov|dec)(\d{4})",
            remote_path,
            re.IGNORECASE,
        )
    if m:
        mon_num = _MONTH_NUMS.get(m.group(1).lower(), 1)
        year = int(m.group(2))
        sort_num = year * 100 + mon_num
        ym = f"{year:04d}-{mon_num:02d}"
        pretty = f"{_MONTH_NAMES[mon_num]} {year}"
        if is_phd:
            pretty += " (Ph.D Entrance)"
        return sort_num, ym, pretty
    return 0, "0000-00", raw or "Unknown Session"


def parse_exam_sessions(html_text: str) -> list[tuple[str, str]]:
    """Parse examid links from dcrustpqp.php."""
    seen: set[str] = set()
    sessions: list[tuple[str, str]] = []
    for eid, label in _EXAM_RE.findall(html_text):
        clean_lbl = html_lib.unescape(re.sub(r"\s+", " ", label)).strip()
        if eid not in seen:
            seen.add(eid)
            sessions.append((eid, clean_lbl))
    return sessions


def _build_remote_url(base_url: str, remote_path: str) -> str:
    clean_rel = remote_path.lstrip("/")
    encoded_path = urllib.parse.quote(clean_rel, safe="/:@-._~")
    return f"{base_url.rstrip('/')}/{encoded_path}"


def parse_letter_pqp_rows(
    html_text: str,
    *,
    exam_id: str,
    session_label: str,
    base_url: str = DCRUSTEDP_BASE_URL,
) -> list[PyqEntry]:
    """Parse subject table rows from pqp.php?letter=<X>."""
    sort_num, ym, pretty_session = parse_session_sort(session_label)
    slug = _sanitize_fs_part(f"{ym}_{re.sub(r'[^A-Za-z0-9]+', '_', session_label).strip('_')}", max_len=48)
    entries: list[PyqEntry] = []
    for href, code_txt, subj_txt in _ROW_RE.findall(html_text):
        rel_path = html_lib.unescape(href).strip()
        raw_code = html_lib.unescape(code_txt).strip()
        subject_name = _normalize_subject_name(subj_txt)
        code = normalize_course_code(raw_code) or normalize_course_code(Path(rel_path).stem)
        if not code:
            continue
        sort_eff, _ym_eff, pretty_eff = (
            (sort_num, ym, pretty_session) if sort_num else parse_session_sort(session_label, rel_path)
        )
        entries.append(
            PyqEntry(
                exam_id=exam_id,
                session_label=pretty_eff,
                session_slug=slug,
                session_sort=sort_eff,
                raw_code=raw_code,
                course_code=code,
                subject_name=subject_name or raw_code,
                remote_path=rel_path,
                remote_url=_build_remote_url(base_url, rel_path),
            )
        )
    return entries


def parse_direct_pdf_links(
    html_text: str,
    *,
    exam_id: str,
    session_label: str,
    base_url: str = DCRUSTEDP_BASE_URL,
) -> list[PyqEntry]:
    """Parse direct PDF links (used on Ph.D Entrance Exam session pages)."""
    sort_num, ym, pretty_session = parse_session_sort(session_label)
    slug = _sanitize_fs_part(f"{ym}_{re.sub(r'[^A-Za-z0-9]+', '_', session_label).strip('_')}", max_len=48)
    entries: list[PyqEntry] = []
    for href, label in _DIRECT_PDF_RE.findall(html_text):
        rel_path = html_lib.unescape(href).strip()
        clean_lbl = _normalize_subject_name(label)
        stem_code = normalize_course_code(Path(rel_path).stem)
        code = f"PHD_{stem_code[:24]}" if "ph" in session_label.lower() else (stem_code or "PYQ")
        entries.append(
            PyqEntry(
                exam_id=exam_id,
                session_label=pretty_session,
                session_slug=slug,
                session_sort=sort_num,
                raw_code=Path(rel_path).stem,
                course_code=code,
                subject_name=f"{clean_lbl} (Ph.D Entrance)" if "ph" in session_label.lower() else clean_lbl,
                remote_path=rel_path,
                remote_url=_build_remote_url(base_url, rel_path),
            )
        )
    return entries


class DcrustPyqClient:
    """HTTP scraper + concurrent PDF fetcher for https://www.dcrustedp.in/dcrustpqp.php."""

    def __init__(self, base_url: str = DCRUSTEDP_BASE_URL, timeout: int = 25):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._ssl_ctx = ssl.create_default_context()
        self._allowed_hosts = set(_APPROVED_PYQ_HOSTS)
        base_host = (urllib.parse.urlsplit(self.base_url).hostname or "").lower()
        if base_host:
            self._allowed_hosts.add(base_host)

    def _validate_url(self, url: str) -> None:
        parsed = urllib.parse.urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme.lower() not in {"http", "https"} or host not in self._allowed_hosts:
            raise ValueError(f"Blocked untrusted PYQ URL: {url}")

    def _make_opener(self) -> urllib.request.OpenerDirector:
        cj = http.cookiejar.CookieJar()
        return urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj),
            urllib.request.HTTPSHandler(context=self._ssl_ctx),
            _SafeHostRedirectHandler(self._allowed_hosts),
        )

    def _get_text(self, opener: urllib.request.OpenerDirector, url: str, referer: str | None = None) -> str:
        self._validate_url(url)
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) SmritiPYQ/1.0"}
        if referer:
            headers["Referer"] = referer
        req = urllib.request.Request(url, headers=headers)
        with opener.open(req, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def _crawl_exam_session(self, exam_id: str, session_label: str) -> list[PyqEntry]:
        opener = self._make_opener()
        index_url = f"{self.base_url}{DCRUSTEDP_INDEX_PATH}"
        # Establish PHP session cookie first
        self._get_text(opener, index_url)
        session_url = f"{self.base_url}{DCRUSTEDP_SESSION_PATH}?examid={urllib.parse.quote(exam_id)}"
        page2 = self._get_text(opener, session_url, referer=index_url)
        if "alphabetsearch" not in page2.lower() and "pqp.php" not in page2.lower():
            return parse_direct_pdf_links(
                page2, exam_id=exam_id, session_label=session_label, base_url=self.base_url
            )

        collected: list[PyqEntry] = []
        seen_keys: set[tuple[str, str]] = set()
        for letter in string.ascii_uppercase:
            letter_url = f"{self.base_url}{DCRUSTEDP_LETTER_PATH}?letter={letter}"
            html_letter = self._get_text(opener, letter_url, referer=session_url)
            for entry in parse_letter_pqp_rows(
                html_letter, exam_id=exam_id, session_label=session_label, base_url=self.base_url
            ):
                key = (entry.course_code, entry.remote_path.lower())
                if key not in seen_keys:
                    seen_keys.add(key)
                    collected.append(entry)
        return collected

    def fetch_catalog(
        self,
        *,
        exam_ids: set[str] | None = None,
        max_workers: int = 6,
        progress_cb: Callable[[str], None] | None = None,
    ) -> tuple[list[dict[str, str]], list[PyqEntry]]:
        opener = self._make_opener()
        index_html = self._get_text(opener, f"{self.base_url}{DCRUSTEDP_INDEX_PATH}")
        sessions = parse_exam_sessions(index_html)
        if exam_ids is not None:
            sessions = [(eid, lbl) for eid, lbl in sessions if eid in exam_ids]

        all_entries: list[PyqEntry] = []
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(sessions) or 1))) as pool:
            futs = {
                pool.submit(self._crawl_exam_session, eid, lbl): (eid, lbl)
                for eid, lbl in sessions
            }
            for fut in as_completed(futs):
                eid, lbl = futs[fut]
                entries = fut.result()
                all_entries.extend(entries)
                if progress_cb:
                    progress_cb(f"Indexed session {lbl} (examid={eid}): {len(entries)} papers")

        all_entries.sort(key=lambda e: (e.course_code, -e.session_sort, e.remote_path))
        session_meta = [{"exam_id": eid, "label": lbl} for eid, lbl in sessions]
        return session_meta, all_entries

    def download_pdf(self, url: str, dest: Path) -> tuple[str, int]:
        """Download a single PDF verifying %PDF header cleanly."""
        try:
            self._validate_url(url)
        except ValueError:
            return "invalid", 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.parent / f".{uuid.uuid4().hex}.pdf.part"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) SmritiPYQ/1.0",
                "Referer": f"{self.base_url}{DCRUSTEDP_LETTER_PATH}",
            },
        )
        opener = self._make_opener()
        for attempt in range(2):
            try:
                with opener.open(req, timeout=self.timeout) as resp:
                    data = resp.read()
                if not data.lstrip()[:5].startswith(b"%PDF"):
                    tmp.unlink(missing_ok=True)
                    return "invalid", 0
                tmp.write_bytes(data)
                tmp.replace(dest)
                return "downloaded", len(data)
            except urllib.error.HTTPError as exc:
                tmp.unlink(missing_ok=True)
                if exc.code in (404, 410):
                    return "missing_remote", 0
                if attempt == 1:
                    return "error", 0
            except (urllib.error.URLError, TimeoutError, OSError):
                tmp.unlink(missing_ok=True)
                if attempt == 1:
                    return "error", 0
        return "error", 0


def _assign_sorted_paths(entries: list[PyqEntry]) -> None:
    """Assign sorted relative paths under by_subject/<CODE> - <NAME>/<YYYY-MM>_<session>_<CODE>.pdf."""
    canonical_names: dict[str, str] = {}
    for e in sorted(entries, key=lambda x: (-x.session_sort, len(x.subject_name))):
        if e.course_code not in canonical_names and e.subject_name:
            canonical_names[e.course_code] = e.subject_name

    used_paths: set[str] = set()
    for e in sorted(entries, key=lambda x: (x.course_code, -x.session_sort, x.remote_path)):
        subj = canonical_names.get(e.course_code, e.subject_name or e.course_code)
        e.subject_name = subj
        folder = _sanitize_fs_part(f"{e.course_code} - {subj}", max_len=84)
        base_stem = _sanitize_fs_part(f"{e.session_slug}_{e.course_code}", max_len=72)
        rel = f"by_subject/{folder}/{base_stem}.pdf"
        suffix = 2
        while rel.lower() in used_paths:
            rel = f"by_subject/{folder}/{base_stem}_{suffix}.pdf"
            suffix += 1
        used_paths.add(rel.lower())
        e.local_relpath = rel


def _hardlink_by_session(pyq_dir: Path, entry: PyqEntry) -> None:
    if not entry.local_relpath:
        return
    src = pyq_dir / entry.local_relpath
    if not src.exists():
        return
    sess_folder = _sanitize_fs_part(entry.session_slug, max_len=48)
    fname = _sanitize_fs_part(f"{entry.course_code} - {entry.subject_name}", max_len=90) + ".pdf"
    dst = pyq_dir / "by_session" / sess_folder / fname
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        pass


def save_pyq_catalog(pyq_dir: Path, catalog: PyqCatalog) -> Path:
    pyq_dir.mkdir(parents=True, exist_ok=True)
    idx_path = pyq_dir / "index.json"
    tmp_path = pyq_dir / "index.json.tmp"
    payload = {
        "source_url": catalog.source_url,
        "updated_at": catalog.updated_at,
        "exam_sessions": catalog.exam_sessions,
        "entries": [asdict(e) for e in catalog.entries],
    }
    tmp_path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    tmp_path.replace(idx_path)
    with _CACHE_LOCK:
        _CATALOG_CACHE.pop(idx_path.resolve(), None)
    return idx_path


def load_pyq_catalog(pyq_dir: Path) -> PyqCatalog | None:
    idx_path = pyq_dir / "index.json"
    if not idx_path.exists():
        return None
    resolved = idx_path.resolve()
    mtime = idx_path.stat().st_mtime
    with _CACHE_LOCK:
        cached = _CATALOG_CACHE.get(resolved)
        if cached and cached[0] == mtime:
            return cached[1]

    raw = json.loads(idx_path.read_text(encoding="utf-8"))
    entries = [PyqEntry(**item) for item in raw.get("entries", [])]
    catalog = PyqCatalog(
        source_url=raw.get("source_url", f"{DCRUSTEDP_BASE_URL}{DCRUSTEDP_INDEX_PATH}"),
        updated_at=raw.get("updated_at", ""),
        entries=entries,
        exam_sessions=raw.get("exam_sessions", []),
    )
    with _CACHE_LOCK:
        _CATALOG_CACHE[resolved] = (mtime, catalog)
    return catalog


def sync_dcrust_pyqs(
    pyq_dir: Path,
    *,
    download: bool = True,
    max_workers: int = 12,
    exam_ids: set[str] | None = None,
    client: DcrustPyqClient | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> PyqCatalog:
    """Crawl dcrustedp.in, download available PDFs into sorted folders, and save index.json."""
    pyq_dir.mkdir(parents=True, exist_ok=True)
    client = client or DcrustPyqClient()

    existing_by_key: dict[tuple[str, str], PyqEntry] = {}
    old = load_pyq_catalog(pyq_dir)
    if old:
        for e in old.entries:
            existing_by_key[(e.exam_id, e.remote_path.lower())] = e

    sessions, entries = client.fetch_catalog(
        exam_ids=exam_ids, max_workers=min(6, max_workers), progress_cb=progress_cb
    )
    _assign_sorted_paths(entries)

    # Carry forward prior 404/downloaded knowledge so incremental runs stay fast
    to_download: list[PyqEntry] = []
    for e in entries:
        prev = existing_by_key.get((e.exam_id, e.remote_path.lower()))
        target = pyq_dir / e.local_relpath
        same_slot = prev is None or not prev.local_relpath or prev.local_relpath == e.local_relpath
        if same_slot and target.exists() and target.stat().st_size > 100:
            e.status = "downloaded"
            e.size_bytes = target.stat().st_size
            _hardlink_by_session(pyq_dir, e)
            continue
        if prev and prev.status in {"missing_remote", "invalid"}:
            e.status = prev.status
            continue
        if download:
            to_download.append(e)

    if download and to_download:
        done = 0
        total = len(to_download)
        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
            futs = {pool.submit(client.download_pdf, e.remote_url, pyq_dir / e.local_relpath): e for e in to_download}
            for fut in as_completed(futs):
                e = futs[fut]
                status, sz = fut.result()
                e.status = status
                e.size_bytes = sz
                if status == "downloaded":
                    _hardlink_by_session(pyq_dir, e)
                done += 1
                if progress_cb and (done % 250 == 0 or done == total):
                    progress_cb(f"Downloaded/checked {done}/{total} PYQ PDFs...")

    if exam_ids is not None and old is not None:
        refreshed_ids = {s.get("exam_id", "") for s in sessions} | set(exam_ids)
        merged_entries = [x for x in old.entries if x.exam_id not in refreshed_ids] + entries
        merged_entries.sort(key=lambda e: (e.course_code, -e.session_sort, e.remote_path))
        by_eid = {s.get("exam_id", ""): s for s in old.exam_sessions if s.get("exam_id")}
        for s in sessions:
            if s.get("exam_id"):
                by_eid[s["exam_id"]] = s
        entries = merged_entries
        sessions = list(by_eid.values())

    catalog = PyqCatalog(
        source_url=f"{client.base_url}{DCRUSTEDP_INDEX_PATH}",
        updated_at=dt.datetime.now(tz=_IST).strftime("%Y-%m-%d %H:%M"),
        entries=entries,
        exam_sessions=sessions,
    )
    save_pyq_catalog(pyq_dir, catalog)
    return catalog


def extract_pyq_subject_query(question: str) -> str:
    """Strip conversational PYQ boilerplate to isolate subject code or subject name."""
    cleaned = _PYQ_BOILERPLATE.sub(" ", question or "")
    cleaned = re.sub(r"[?!.,:;\"'()\[\]{}]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        m = _COURSE_CODE_RE.search(question or "")
        return m.group(1) if m else ""
    return cleaned


def _score_subject_match(
    cleaned_query: str,
    query_codes: list[str],
    query_tokens: list[str],
    expanded_tokens: list[str],
    course_code: str,
    subject_name: str,
) -> float:
    code_norm = normalize_course_code(course_code)
    subj_tokens = _search_tokens(subject_name)
    subj_token_set = set(subj_tokens)
    subj_phrase = " ".join(subj_tokens)
    q_phrase = " ".join(expanded_tokens or query_tokens)

    # 1. Exact or base course-code match
    for qc in query_codes:
        if qc == code_norm:
            return 100.0
        if len(qc) >= 4 and (code_norm.startswith(qc) or qc.startswith(code_norm)):
            return 90.0
        # Match numeric core + dept prefix ignoring final scheme suffix e.g. CSE302 vs CSE302C
        qc_base = re.sub(r"[A-Z]+$", "", qc)
        code_base = re.sub(r"[A-Z]+$", "", code_norm)
        if len(qc_base) >= 4 and qc_base == code_base:
            return 88.0

    if not q_phrase:
        return 0.0

    # 2. Subject-name exact / phrase match
    if q_phrase == subj_phrase:
        return 85.0
    if len(q_phrase) >= 4 and q_phrase in subj_phrase:
        coverage = len(q_phrase) / max(len(subj_phrase), 1)
        return 72.0 + coverage * 10.0

    # 3. Token subset match (all query tokens appear in subject name)
    q_set = set(expanded_tokens or query_tokens)
    if q_set and q_set <= subj_token_set:
        jaccard = len(q_set) / max(len(subj_token_set), 1)
        return 55.0 + jaccard * 20.0

    # 4. Partial token overlap + sequence similarity fallback
    if q_set and subj_token_set:
        overlap = len(q_set & subj_token_set) / len(q_set)
        seq = SequenceMatcher(None, q_phrase, subj_phrase).ratio()
        combined = overlap * 45.0 + seq * 20.0
        if overlap >= 0.5 or seq >= 0.72:
            return combined
    return 0.0


def search_pyqs(
    query: str,
    pyq_dir: Path,
    *,
    catalog: PyqCatalog | None = None,
    max_subjects: int = 8,
) -> PyqSearchResult:
    """Search the local PYQ catalog by subject code or subject name."""
    cat = catalog or load_pyq_catalog(pyq_dir)
    cleaned = extract_pyq_subject_query(query)
    if cat is None or not cat.entries:
        return PyqSearchResult(
            raw_query=query,
            cleaned_query=cleaned,
            matches=[],
            total_papers=0,
            catalog_total_entries=0,
            catalog_ready=False,
        )

    raw_codes = [normalize_course_code(m) for m in _COURSE_CODE_RE.findall(query)]
    query_codes = [c for c in raw_codes if re.search(r"\d", c)]
    base_tokens = _search_tokens(cleaned)
    expanded_tokens = list(base_tokens)
    if len(base_tokens) == 1 and base_tokens[0] in ABBREVIATION_ALIASES:
        expanded_tokens = _search_tokens(ABBREVIATION_ALIASES[base_tokens[0]])

    grouped: dict[str, list[PyqEntry]] = {}
    for e in cat.entries:
        grouped.setdefault(e.course_code, []).append(e)

    scored_groups: list[PyqSubjectGroup] = []
    for code, items in grouped.items():
        # Prefer entries with an actual PDF (or at least non-invalid) sorted newest first
        sorted_items = sorted(items, key=lambda x: (-x.session_sort, x.session_label))
        subj_name = next((i.subject_name for i in sorted_items if i.subject_name), code)
        score = _score_subject_match(cleaned, query_codes, base_tokens, expanded_tokens, code, subj_name)
        if score >= 38.0:
            # Prefer downloaded/available entries over broken remote 404s if both exist, else keep all valid
            visible = [i for i in sorted_items if i.status != "missing_remote"] or sorted_items
            scored_groups.append(
                PyqSubjectGroup(
                    course_code=code,
                    subject_name=subj_name,
                    score=score,
                    entries=visible,
                )
            )

    scored_groups.sort(key=lambda g: (-g.score, -len(g.entries), g.course_code))
    if scored_groups and scored_groups[0].score >= 85.0:
        scored_groups = [g for g in scored_groups if g.score >= 70.0]
    elif scored_groups and scored_groups[0].score >= 55.0:
        scored_groups = [g for g in scored_groups if g.score >= 48.0]

    top = scored_groups[:max_subjects]
    total_papers = sum(len(g.entries) for g in top)
    return PyqSearchResult(
        raw_query=query,
        cleaned_query=cleaned,
        matches=top,
        total_papers=total_papers,
        catalog_total_entries=len(cat.entries),
        catalog_ready=True,
    )


def format_pyq_markdown(result: PyqSearchResult, pyq_dir: Path) -> str:
    """Format matched PYQs cleanly as Markdown sorted newest-first."""
    if not result.catalog_ready:
        return (
            f"No local DCRUST PYQ catalog found in `{pyq_dir}` yet.\n\n"
            "Run `smriti pyq sync` in your terminal to download and sort all available papers from `dcrustedp.in`."
        )
    if not result.matches:
        q = result.cleaned_query or result.raw_query
        return (
            f"No DCRUST previous year question papers matched **`{q}`** "
            f"across {result.catalog_total_entries:,} indexed papers.\n\n"
            "Try a full subject code (like `CSE302C`, `CSE405C`, `BT221C`) or subject name (like `Compiler Design`, `Soft Computing`)."
        )

    lines = [
        f"### DCRUST Previous Year Papers · {result.total_papers} paper{'s' if result.total_papers != 1 else ''} found",
        f"Query: `{result.cleaned_query or result.raw_query}` · Sorted newest to oldest",
        "",
    ]
    for grp in result.matches:
        lines.append(f"#### {grp.subject_name} (`{grp.course_code}` · {len(grp.entries)} papers)")
        lines.append("| Exam Session | Code | Status | Local File | Portal |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for e in grp.entries:
            local_p = pyq_dir / e.local_relpath if e.local_relpath else None
            is_local = bool(local_p and local_p.exists())
            status_txt = f"Saved ({max(1, e.size_bytes // 1024)} KB)" if is_local else (
                "Remote 404" if e.status == "missing_remote" else "Portal link"
            )
            local_col = f"`{e.local_relpath}`" if is_local else "—"
            lines.append(
                f"| **{e.session_label}** | `{e.raw_code or e.course_code}` | {status_txt} | {local_col} | [Open PDF]({e.remote_url}) |"
            )
        lines.append("")
    return "\n".join(lines).strip()


def pyq_to_ui_props(result: PyqSearchResult, pyq_dir: Path) -> dict:
    """Build JSON props for Chainlit `DcrustPyqs.jsx` CustomElement."""
    groups_out = []
    for grp in result.matches:
        papers = []
        for e in grp.entries:
            local_p = pyq_dir / e.local_relpath if e.local_relpath else None
            is_local = bool(local_p and local_p.exists())
            papers.append(
                {
                    "session": e.session_label,
                    "sessionSort": e.session_sort,
                    "code": e.raw_code or e.course_code,
                    "remoteUrl": e.remote_url,
                    "localRelpath": e.local_relpath,
                    "downloaded": is_local,
                    "sizeKb": max(1, e.size_bytes // 1024) if is_local else 0,
                    "status": e.status,
                }
            )
        groups_out.append(
            {
                "courseCode": grp.course_code,
                "subjectName": grp.subject_name,
                "count": len(papers),
                "papers": papers,
            }
        )
    return {
        "query": result.cleaned_query or result.raw_query,
        "totalPapers": result.total_papers,
        "catalogTotal": result.catalog_total_entries,
        "pyqDir": str(pyq_dir),
        "groups": groups_out,
    }


def format_pyq_html(result: PyqSearchResult, pyq_dir: Path) -> str:
    """Render a standalone clean HTML browser view for matched PYQs."""
    sections = []
    for grp in result.matches:
        rows = []
        for e in grp.entries:
            local_p = pyq_dir / e.local_relpath if e.local_relpath else None
            is_local = bool(local_p and local_p.exists())
            badge = (
                f'<span class="ok">Saved ({max(1, e.size_bytes // 1024)} KB)</span>'
                if is_local
                else '<span class="muted">Portal only</span>'
            )
            local_link = (
                f'<a href="{html_lib.escape(local_p.resolve().as_uri())}">Local PDF</a>'
                if is_local and local_p is not None
                else "—"
            )
            rows.append(
                f"<tr><td><strong>{html_lib.escape(e.session_label)}</strong></td>"
                f"<td><code>{html_lib.escape(e.raw_code or e.course_code)}</code></td>"
                f"<td>{badge}</td>"
                f"<td>{local_link}</td>"
                f'<td><a href="{html_lib.escape(e.remote_url)}" target="_blank" rel="noopener">dcrustedp.in ↗</a></td></tr>'
            )
        sections.append(
            f'<div class="card"><div class="card-h"><span>{html_lib.escape(grp.subject_name)}</span>'
            f'<span class="pill">{html_lib.escape(grp.course_code)} · {len(grp.entries)} papers</span></div>'
            f'<table><thead><tr><th>Session</th><th>Code</th><th>Status</th><th>Local</th><th>Portal</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
        )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>DCRUST PYQs · {html_lib.escape(result.cleaned_query or result.raw_query)}</title>
<style>
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:#f8fafc; color:#0f172a; margin:0; padding:1.5rem; }}
.wrap {{ max-width:960px; margin:0 auto; }}
h1 {{ font-size:1.35rem; margin:0 0 0.25rem; }}
.sub {{ color:#475569; font-size:0.86rem; margin-bottom:1.25rem; }}
.card {{ background:#fff; border:1px solid #e2e8f0; border-radius:0.85rem; margin-bottom:1rem; overflow:hidden; }}
.card-h {{ display:flex; justify-content:space-between; align-items:center; padding:0.85rem 1rem; background:#f8fafc; border-bottom:1px solid #e2e8f0; font-weight:700; }}
.pill {{ background:#eef2ff; color:#4f46e5; font-size:0.75rem; padding:2px 10px; border-radius:999px; }}
table {{ width:100%; border-collapse:collapse; font-size:0.85rem; }}
th, td {{ padding:0.6rem 0.9rem; border-bottom:1px solid #f1f5f9; text-align:left; }}
th {{ font-size:0.74rem; color:#64748b; text-transform:uppercase; }}
.ok {{ color:#047857; font-weight:600; }}
.muted {{ color:#64748b; }}
a {{ color:#4f46e5; text-decoration:none; font-weight:600; }}
a:hover {{ text-decoration:underline; }}
</style></head><body><div class="wrap">
<h1>DCRUST Previous Year Question Papers</h1>
<div class="sub">Query: <strong>{html_lib.escape(result.cleaned_query or result.raw_query)}</strong> · {result.total_papers} papers found</div>
{"".join(sections) or "<p>No matching papers found.</p>"}
</div></body></html>"""
