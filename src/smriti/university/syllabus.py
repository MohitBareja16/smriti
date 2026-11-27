"""DCRUST university syllabus catalog, downloader, sorter, and branch/year search."""

from __future__ import annotations

import datetime as dt
import html as html_lib
import json
import os
import re
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    _IST: dt.tzinfo = ZoneInfo("Asia/Kolkata")
except ZoneInfoNotFoundError:
    _IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")
_APPROVED_SYLLABUS_HOSTS = {
    "api.dcrust.online",
    "cse.dcrust.online",
    "dcrust.online",
    "www.dcrust.online",
    "drive.google.com",
    "docs.google.com",
    "dcrustm.ac.in",
    "www.dcrustm.ac.in",
}


class _SafeHostRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: set[str]):
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        host = (parsed.hostname or "").lower()
        if parsed.scheme.lower() not in {"http", "https"} or (
            host not in self.allowed_hosts and not host.endswith(".googleusercontent.com")
        ):
            raise urllib.error.URLError(f"Blocked redirect to untrusted host: {host or newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

SYLLABUS_API_URL = "https://api.dcrust.online/api/syllabus"
SYLLABUS_PAGE_URL = "https://cse.dcrust.online/syllabus"
SYLLABUS_SITE_URL = "https://cse.dcrust.online"

DEPARTMENTS: dict[str, str] = {
    "cse_it": "Computer Science & IT",
    "ece": "Electronics & Comm (ECE)",
    "ee_eee": "Electrical & EEE",
    "mech_aero": "Mechanical & Aerospace",
    "civil": "Civil & Construction",
    "bio_chem": "Biotech & Chemical",
    "arch": "Architecture & Design",
    "bca_mca": "Computer Applications (BCA/MCA)",
    "mgmt": "Management (BBA/MBA)",
    "sciences": "Sciences (Maths, Physics, Chem)",
    "edu_sports": "Education & Sports",
    "common_1st": "Common 1st Year (B.Tech)",
    "ordinances": "Ordinances & Notifications",
}

YEAR_LABELS: dict[str, str] = {
    "1st": "1st Year",
    "2nd": "2nd Year",
    "3rd": "3rd Year",
    "4th": "4th Year",
    "complete": "Complete Scheme",
}

_BRANCH_QUERY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("cse_it", re.compile(r"\b(?:cse|cs|computer\s+science|computer\s+engg|information\s+tech(?:nology)?)\b", re.IGNORECASE)),
    ("ece", re.compile(r"\b(?:ece|electronics(?:\s+(?:and|&)\s+comm\w*)?|vlsi)\b", re.IGNORECASE)),
    ("ee_eee", re.compile(r"\b(?:eee|ee|electrical(?:\s+(?:and|&)\s+electronics)?|power\s+system|renewable\s+energy)\b", re.IGNORECASE)),
    ("mech_aero", re.compile(r"\b(?:mech(?:anical)?|me|auto(?:mobile)?|aero(?:nautical|space)?)\b", re.IGNORECASE)),
    ("civil", re.compile(r"\b(?:civil|ce|structural|highway|construction|building\s+tech\w*)\b", re.IGNORECASE)),
    ("bio_chem", re.compile(r"\b(?:biotech\w*|bio\s*tech|bt|chemical|che|biomed\w*|bme|food\s*tech)\b", re.IGNORECASE)),
    ("arch", re.compile(r"\b(?:arch(?:itecture)?|b\.?\s*arch|interior\s+design|bid|urban\s+planning|m\.?\s*plan)\b", re.IGNORECASE)),
    ("bca_mca", re.compile(r"\b(?:bca|mca|computer\s+applications?)\b", re.IGNORECASE)),
    ("mgmt", re.compile(r"\b(?:bba|mba|management|commerce|dms|humanities)\b", re.IGNORECASE)),
    ("sciences", re.compile(r"\b(?:b\.?\s*sc|m\.?\s*sc|math(?:ematic)?s|physics|chemistry|nanotech\w*)\b", re.IGNORECASE)),
    ("edu_sports", re.compile(r"\b(?:b\.?\s*ed|m\.?\s*ed|physical\s+edu\w*|sports|bped|bpes|mpes)\b", re.IGNORECASE)),
    ("ordinances", re.compile(r"\b(?:ordinance|amendment|notification|bos\s+minutes)\b", re.IGNORECASE)),
]

_YEAR_QUERY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("1st", re.compile(r"\b(?:1st\s*(?:yr|year)|first\s*year|sem(?:ester)?\s*[12]|i+\s*(?:st)?\s*year|1st\s*sem|2nd\s*sem)\b", re.IGNORECASE)),
    ("2nd", re.compile(r"\b(?:2nd\s*(?:yr|year)|second\s*year|sem(?:ester)?\s*[34]|3rd\s*sem|4th\s*sem)\b", re.IGNORECASE)),
    ("3rd", re.compile(r"\b(?:3rd\s*(?:yr|year)|third\s*year|sem(?:ester)?\s*[56]|5th\s*sem|6th\s*sem)\b", re.IGNORECASE)),
    ("4th", re.compile(r"\b(?:4th\s*(?:yr|year)|fourth\s*year|final\s*year|sem(?:ester)?\s*[78]|7th\s*sem|8th\s*sem)\b", re.IGNORECASE)),
    ("complete", re.compile(r"\b(?:complete\s*(?:scheme|syllabus)?|all\s*years|full\s*(?:scheme|syllabus))\b", re.IGNORECASE)),
]

_DEGREE_QUERY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("B.Tech", re.compile(r"\b(?:b\.?\s*tech|btech)\b", re.IGNORECASE)),
    ("M.Tech", re.compile(r"\b(?:m\.?\s*tech|mtech)\b", re.IGNORECASE)),
    ("BCA", re.compile(r"\bbca\b", re.IGNORECASE)),
    ("MCA", re.compile(r"\bmca\b", re.IGNORECASE)),
    ("BBA", re.compile(r"\bbba\b", re.IGNORECASE)),
    ("MBA", re.compile(r"\bmba\b", re.IGNORECASE)),
    ("B.Arch", re.compile(r"\bb\.?\s*arch\b", re.IGNORECASE)),
    ("B.I.D", re.compile(r"\b(?:b\.?\s*i\.?\s*d|interior\s+design)\b", re.IGNORECASE)),
    ("B.Sc / M.Sc", re.compile(r"\b(?:b\.?\s*sc|m\.?\s*sc|integrated\s+bsc)\b", re.IGNORECASE)),
]

_SYLLABUS_BOILERPLATE = re.compile(
    r"\b(?:dcrust|university|official|latest|complete|full|new|old|scheme|and|syllabi|syllabus|"
    r"show|give|get|find|list|fetch|download|send|open|check|search|for|of|the|me|my|in|on|"
    r"branch|year|yr|sem|semester|please|all|available)\b",
    re.IGNORECASE,
)

_CATALOG_CACHE: dict[Path, tuple[float, SyllabusCatalog]] = {}
_CACHE_LOCK = threading.Lock()


@dataclass
class SyllabusEntry:
    """Single university syllabus/scheme entry from cse.dcrust.online/syllabus."""

    title: str
    raw_text: str
    remote_url: str
    department_id: str
    department_label: str
    degree: str
    degree_category: str
    year_id: str
    year_label: str
    covered_years: list[str] = field(default_factory=list)
    file_type: str = "PDF"
    scheme: str | None = None
    session_year: str | None = None
    session_sort: int = 0
    local_relpath: str = ""
    status: str = "pending"  # pending | downloaded | portal_only | missing_remote | error
    size_bytes: int = 0


@dataclass
class SyllabusCatalog:
    """Complete syllabus catalog persisted at syllabus/index.json."""

    source_url: str
    updated_at: str
    entries: list[SyllabusEntry] = field(default_factory=list)


@dataclass
class SyllabusSearchResult:
    """Matched syllabi filtered by branch, year, degree, and keywords."""

    raw_query: str
    branch_id: str | None
    branch_label: str | None
    year_id: str | None
    year_label: str | None
    degree: str | None
    matches: list[SyllabusEntry] = field(default_factory=list)
    catalog_total_entries: int = 0
    catalog_ready: bool = True


def _sanitize_fs_part(text: str, max_len: int = 76) -> str:
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", text or "")
    clean = re.sub(r"\s+", " ", clean).strip(" .-_")
    if len(clean) > max_len:
        clean = clean[:max_len].rstrip(" .-_")
    return clean or "syllabus"


def _clean_title(raw: str) -> str:
    if not raw:
        return "Syllabus Document"
    txt = html_lib.unescape(raw)
    txt = re.sub(r"\.(?:docx?|pdf)$", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"[\r\n\t_\s]+", " ", txt).strip()
    txt = re.sub(r"\b!st\b|\bIst\b", "1st", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\b2ny\b", "2nd", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\bSylabus\b", "Syllabus", txt, flags=re.IGNORECASE)
    return txt


def _parse_covered_years(raw_text: str, primary_year: str) -> list[str]:
    years: set[str] = set()
    if primary_year in {"1st", "2nd", "3rd", "4th"}:
        years.add(primary_year)
    if re.search(r"\b1\s*(?:-|to)\s*6\b|1\s+6\b", raw_text, re.IGNORECASE):
        years.update({"1st", "2nd", "3rd"})
    if re.search(r"\b3\s*(?:-|to)\s*8\b|3\s+8\b", raw_text, re.IGNORECASE):
        years.update({"2nd", "3rd", "4th"})
    if re.search(r"\b(?:1\s*(?:-|to)\s*8|complete|4\s*year|main\s*ee|main\s*eee)\b", raw_text, re.IGNORECASE):
        years.update({"1st", "2nd", "3rd", "4th"})
    if not years and primary_year == "complete":
        years.update({"1st", "2nd", "3rd", "4th"})
    return sorted(years)


def _extract_session_sort(text: str, url: str) -> tuple[str | None, int]:
    m = re.search(r"\b(20[12][0-9](?:[\s\-_]2[0-9])?)\b", text)
    if m:
        yr = int(m.group(1)[:4])
        return m.group(1).replace(" ", "-"), yr * 100
    u_m = re.search(r"/File(20[12]\d)(\d{2})", url)
    if u_m:
        yr, mo = int(u_m.group(1)), int(u_m.group(2))
        return f"{yr}", yr * 100 + mo
    u_y = re.search(r"/(20[12]\d)/", url)
    if u_y:
        return u_y.group(1), int(u_y.group(1)) * 100
    return None, 0


def classify_syllabus_item(raw: dict[str, str]) -> SyllabusEntry:
    """Classify a raw {text, url} syllabus record using branch, degree, year, and scheme rules."""
    raw_text = (raw.get("text") or "").strip()
    url = (raw.get("url") or "").strip()
    combined = f"{raw_text} {url}"
    combined = re.sub(r"!st\b|\bIst\b", "1st", combined, flags=re.IGNORECASE)
    combined = re.sub(r"sylabus", "syllabus", combined, flags=re.IGNORECASE)
    combined = re.sub(r"([a-z])([A-Z])", r"\1 \2", combined)
    norm = re.sub(r"[_\.\-/\\()&,;:\r\n\t]+", " ", combined)
    norm = re.sub(r"\s+", " ", norm).strip().lower()
    text_norm = re.sub(r"[_\.\-/\\()&,;:\r\n\t]+", " ", re.sub(r"([a-z])([A-Z])", r"\1 \2", raw_text)).lower()

    degree, degree_cat = "Other", "Other"
    if re.search(r"\b(?:b\s?tech|btech)\b", norm):
        degree, degree_cat = "B.Tech", "B.Tech"
    elif re.search(r"\b(?:m\s?tech|mtech|mt)\b", norm):
        degree, degree_cat = "M.Tech", "M.Tech"
    elif re.search(r"\bbca\b", norm):
        degree, degree_cat = "BCA", "BCA / MCA"
    elif re.search(r"\bmca\b", norm):
        degree, degree_cat = "MCA", "BCA / MCA"
    elif re.search(r"\bbba\b", norm):
        degree, degree_cat = "BBA", "BBA / MBA"
    elif re.search(r"\bmba\b", norm):
        degree, degree_cat = "MBA", "BBA / MBA"
    elif re.search(r"\b(?:b\s?arch|barch)\b", norm):
        degree, degree_cat = "B.Arch", "B.Arch / Design"
    elif re.search(r"\b(?:m\s?arch|march|m\s?plan|murp)\b", norm):
        degree, degree_cat = "M.Arch/M.Plan", "B.Arch / Design"
    elif re.search(r"\b(?:b\s?i\s?d|bid|interior design)\b", norm):
        degree, degree_cat = "B.I.D", "B.Arch / Design"
    elif re.search(r"\b(?:b\s?sc|m\s?sc|bsc|msc|integrated bsc)\b", norm):
        degree, degree_cat = "B.Sc / M.Sc", "Sciences"
    elif re.search(r"\b(?:b\s?ed|m\s?ed|bed|med)\b", norm):
        degree, degree_cat = "B.Ed / M.Ed", "Education & Sports"
    elif re.search(r"\b(?:b\s?p\s?ed|b\s?p\s?e\s?s|m\s?p\s?e\s?s|bped|bpes|mpes)\b", norm):
        degree, degree_cat = "Physical Education", "Education & Sports"
    elif re.search(r"\b(?:ph\s?d|phd)\b", norm):
        degree, degree_cat = "Ph.D", "Other"

    dept_id = "ordinances"
    if re.search(r"\b(?:cse|computer science|computer engg|it|information tech)\b", norm):
        dept_id = "cse_it"
    elif re.search(r"\b(?:bca|mca)\b", norm):
        dept_id = "bca_mca"
    elif re.search(r"\b(?:ece|electronics|vlsi|mtec ece)\b", norm):
        dept_id = "ece"
    elif re.search(r"\b(?:eee|electrical electronics)\b", norm) or re.search(
        r"\b(?:ee|electrical|power system|instrumentation|eeic|eem|eefinal)\b", norm
    ):
        dept_id = "ee_eee"
    elif re.search(r"\b(?:me|mechanical|mech|auto|automobile|aero|aeronautical)\b", norm):
        dept_id = "mech_aero"
    elif re.search(r"\b(?:civil|ce|structural|highway|crem|c rem|building technology)\b", norm):
        dept_id = "civil"
    elif re.search(
        r"\b(?:che|chem engg|chemical|bt|biotech|bio\s?tech|ft|food tech|bme|bio\s?med|biomedical|bio medical)\b",
        norm,
    ) and not re.search(r"\bm\s?sc.*chem", norm):
        dept_id = "bio_chem"
    elif re.search(r"\b(?:arch|architecture|interior design|bid|b i d|planning|urp|m plan|sustainable arch|mcrm)\b", norm):
        dept_id = "arch"
    elif re.search(r"\b(?:re|renewable energy|energy studies|ceees)\b", norm):
        dept_id = "ee_eee"
    elif re.search(r"\b(?:msn|msnt|materials science|nanotechnology)\b", norm):
        dept_id = "sciences"
    elif re.search(r"\b(?:bba|mba|dms|commerce|management|mdc)\b", norm):
        dept_id = "mgmt"
    elif re.search(r"\b(?:math|maths|mathematics|phys|physics|phy|chemistry|chem)\b", norm):
        dept_id = "sciences"
    elif re.search(r"\benglish\b", norm):
        dept_id = "mgmt"
    elif re.search(r"\b(?:b\s?ed|m\s?ed|bed|med|spl\s?ed|spl\s?edu|p\s?ed|p\s?e\s?s|bped|bpes|mpes)\b", norm):
        dept_id = "edu_sports"
    elif re.search(
        r"common for all branches|first\s*year.*b\s?tech|b\s?tech.*(?:1st|first)\s*year|"
        r"syllabus\s*first\s*year",
        norm,
    ):
        dept_id = "common_1st"

    if re.search(r"\b(?:bos minutes|forwarding letter|proforma|amendment)\b", text_norm) or (
        dept_id == "ordinances" and "ordinance" in text_norm
    ):
        dept_id = "ordinances"

    year_id = "complete"
    if re.search(r"\b(?:1st\s?year|first\s?year|1st\s?to\s?2nd|sem\s?1|semester\s?1|1\s?2\s?sem|syllabus\s*first)\b", norm):
        year_id = "1st"
    elif re.search(r"\b(?:2nd\s?year|2ny\s?year|2\s?year|second\s?year|3\s?4\s?sem|3rd\s?to\s?4th)\b", norm):
        year_id = "2nd"
    elif re.search(r"\b(?:3rd\s?year|3\s?year|third\s?year|v\s?vi\s?sem|v\s?vi|5\s?6\s?sem|5th\s?to\s?6th)\b", norm):
        year_id = "3rd"
    elif re.search(r"\b(?:4th\s?year|4\s?year|fourth\s?year|vii\s?viii|vii\s?to\s?x|7\s?8\s?sem)\b", norm):
        year_id = "4th"

    file_type = "PDF"
    if re.search(r"\.docx\b", url, re.IGNORECASE):
        file_type = "DOCX"
    elif re.search(r"\.doc\b", url, re.IGNORECASE):
        file_type = "DOC"
    elif "drive.google.com" in url.lower():
        file_type = "DRIVE"

    scheme = None
    if re.search(r"nep[\s\-]2020", norm):
        scheme = "NEP-2020"
    elif re.search(r"c\s?scheme", norm):
        scheme = "C-Scheme"
    elif re.search(r"scheme\s?b", norm):
        scheme = "Scheme-B"

    session_yr, session_sort = _extract_session_sort(raw_text, url)
    return SyllabusEntry(
        title=_clean_title(raw_text),
        raw_text=raw_text,
        remote_url=url,
        department_id=dept_id,
        department_label=DEPARTMENTS[dept_id],
        degree=degree,
        degree_category=degree_cat,
        year_id=year_id,
        year_label=YEAR_LABELS[year_id],
        covered_years=_parse_covered_years(raw_text, year_id),
        file_type=file_type,
        scheme=scheme,
        session_year=session_yr,
        session_sort=session_sort,
    )


def parse_syllabus_api_payload(payload: dict | list) -> list[SyllabusEntry]:
    """Parse `/api/syllabus` JSON response or raw list into classified entries."""
    items = payload.get("data", []) if isinstance(payload, dict) else payload
    seen_urls: set[str] = set()
    entries: list[SyllabusEntry] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        url = str(item["url"]).strip()
        key = url.lower()
        if key in seen_urls:
            continue
        seen_urls.add(key)
        entries.append(classify_syllabus_item({"text": str(item.get("text") or ""), "url": url}))
    return entries


def _download_url_for(remote_url: str) -> str:
    m = re.search(r"drive\.google\.com/file/d/([^/?#]+)", remote_url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    parsed = urllib.parse.urlsplit(remote_url)
    encoded_path = urllib.parse.quote(urllib.parse.unquote(parsed.path), safe="/:@-._~")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, encoded_path, parsed.query, ""))


def _extension_for(entry: SyllabusEntry, data: bytes | None = None) -> str:
    path_ext = Path(urllib.parse.urlsplit(entry.remote_url).path).suffix.lower()
    if path_ext in {".pdf", ".docx", ".doc"}:
        return path_ext
    if data and data.lstrip()[:5].startswith(b"%PDF"):
        return ".pdf"
    if data and data[:2] == b"PK":
        return ".docx"
    return ".pdf"


class DcrustSyllabusClient:
    """Fetcher + file downloader for https://cse.dcrust.online/syllabus."""

    def __init__(self, api_url: str = SYLLABUS_API_URL, page_url: str = SYLLABUS_PAGE_URL, timeout: int = 30):
        self.api_url = api_url
        self.page_url = page_url
        self.timeout = timeout
        self._ssl_ctx = ssl.create_default_context()
        self._allowed_hosts = set(_APPROVED_SYLLABUS_HOSTS)
        for u in (self.api_url, self.page_url):
            h = (urllib.parse.urlsplit(u).hostname or "").lower()
            if h:
                self._allowed_hosts.add(h)

    def _validate_url(self, url: str) -> None:
        parsed = urllib.parse.urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme.lower() not in {"http", "https"} or (
            host not in self._allowed_hosts and not host.endswith(".googleusercontent.com")
        ):
            raise ValueError(f"Blocked untrusted syllabus URL: {url}")

    def _get_bytes(self, url: str) -> tuple[bytes, str]:
        self._validate_url(url)
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self._ssl_ctx),
            _SafeHostRedirectHandler(self._allowed_hosts),
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) SmritiSyllabus/1.0"},
        )
        with opener.open(req, timeout=self.timeout) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            return resp.read(), ctype

    def fetch_catalog(self) -> list[SyllabusEntry]:
        try:
            raw, _ = self._get_bytes(self.api_url)
            payload = json.loads(raw.decode("utf-8", errors="replace"))
            entries = parse_syllabus_api_payload(payload)
            if entries:
                return entries
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            pass

        # Fallback: extract Syllabus-*.js chunk embedded list from cse.dcrust.online
        page_html, _ = self._get_bytes(self.page_url)
        html_str = page_html.decode("utf-8", errors="replace")
        m_js = re.search(r'src="(/assets/index-[^"]+\.js)"', html_str)
        if not m_js:
            raise RuntimeError("Could not locate main bundle on cse.dcrust.online/syllabus")
        idx_js, _ = self._get_bytes(f"{SYLLABUS_SITE_URL}{m_js.group(1)}")
        m_syl = re.search(r"import\(`\./(Syllabus-[^`]+\.js)`\)", idx_js.decode("utf-8", errors="replace"))
        if not m_syl:
            raise RuntimeError("Could not locate Syllabus chunk reference")
        syl_js, _ = self._get_bytes(f"{SYLLABUS_SITE_URL}/assets/{m_syl.group(1)}")
        m_json = re.search(r"JSON\.parse\(`(.*?)`\)", syl_js.decode("utf-8", errors="replace"), re.DOTALL)
        if not m_json:
            raise RuntimeError("Could not parse Syllabus chunk JSON payload")
        unescaped = re.sub(r"\\x([0-9A-Fa-f]{2})", lambda mm: chr(int(mm.group(1), 16)), m_json.group(1))
        return parse_syllabus_api_payload(json.loads(unescaped))

    def download_document(self, entry: SyllabusEntry, dest: Path) -> tuple[str, int, Path]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = _download_url_for(entry.remote_url)
        try:
            self._validate_url(url)
        except ValueError:
            return "invalid", 0, dest
        for attempt in range(2):
            try:
                data, ctype = self._get_bytes(url)
                head = data.lstrip()[:64].lower()
                if "text/html" in ctype or head.startswith((b"<!doctype", b"<html", b"<head")):
                    return ("portal_only" if "drive.google.com" in entry.remote_url else "missing_remote"), 0, dest
                ext = _extension_for(entry, data)
                valid_magic = (
                    (ext == ".pdf" and data.lstrip()[:5].startswith(b"%PDF"))
                    or (ext == ".docx" and data[:4] in {b"PK\x03\x04", b"PK\x05\x06"})
                    or (ext == ".doc" and data[:4] == b"\xd0\xcf\x11\xe0")
                )
                if len(data) < 32 or not valid_magic:
                    return "invalid", 0, dest
                final_dest = dest.with_suffix(ext)
                tmp = final_dest.parent / f".{uuid.uuid4().hex}{ext}.part"
                tmp.write_bytes(data)
                tmp.replace(final_dest)
                return "downloaded", len(data), final_dest
            except urllib.error.HTTPError as exc:
                if exc.code in (403, 404, 410):
                    return "missing_remote", 0, dest
                if attempt == 1:
                    return "error", 0, dest
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == 1:
                    return "error", 0, dest
        return "error", 0, dest


def _assign_sorted_paths(entries: list[SyllabusEntry]) -> None:
    used: set[str] = set()
    for e in sorted(entries, key=lambda x: (x.department_id, x.year_id, -x.session_sort, x.title.lower())):
        branch_dir = _sanitize_fs_part(f"{e.department_id} - {e.department_label}", max_len=64)
        year_dir = _sanitize_fs_part(f"{e.year_id} - {e.year_label}", max_len=40)
        ext = _extension_for(e)
        stem = _sanitize_fs_part(e.title, max_len=84)
        rel = f"by_branch/{branch_dir}/{year_dir}/{stem}{ext}"
        idx = 2
        while rel.lower() in used:
            rel = f"by_branch/{branch_dir}/{year_dir}/{stem}_{idx}{ext}"
            idx += 1
        used.add(rel.lower())
        e.local_relpath = rel


def _hardlink_by_year(syllabus_dir: Path, entry: SyllabusEntry) -> None:
    if not entry.local_relpath:
        return
    src = syllabus_dir / entry.local_relpath
    if not src.exists():
        return
    year_dir = _sanitize_fs_part(f"{entry.year_id} - {entry.year_label}", max_len=40)
    fname = _sanitize_fs_part(f"{entry.department_label} - {entry.title}", max_len=96) + src.suffix
    dst = syllabus_dir / "by_year" / year_dir / fname
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        pass


def save_syllabus_catalog(syllabus_dir: Path, catalog: SyllabusCatalog) -> Path:
    syllabus_dir.mkdir(parents=True, exist_ok=True)
    idx_path = syllabus_dir / "index.json"
    tmp_path = syllabus_dir / "index.json.tmp"
    payload = {
        "source_url": catalog.source_url,
        "updated_at": catalog.updated_at,
        "entries": [asdict(e) for e in catalog.entries],
    }
    tmp_path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    tmp_path.replace(idx_path)
    with _CACHE_LOCK:
        _CATALOG_CACHE.pop(idx_path.resolve(), None)
    return idx_path


def load_syllabus_catalog(syllabus_dir: Path) -> SyllabusCatalog | None:
    idx_path = syllabus_dir / "index.json"
    if not idx_path.exists():
        return None
    resolved = idx_path.resolve()
    mtime = idx_path.stat().st_mtime
    with _CACHE_LOCK:
        cached = _CATALOG_CACHE.get(resolved)
        if cached and cached[0] == mtime:
            return cached[1]
    raw = json.loads(idx_path.read_text(encoding="utf-8"))
    entries = [SyllabusEntry(**item) for item in raw.get("entries", [])]
    catalog = SyllabusCatalog(
        source_url=raw.get("source_url", SYLLABUS_PAGE_URL),
        updated_at=raw.get("updated_at", ""),
        entries=entries,
    )
    with _CACHE_LOCK:
        _CATALOG_CACHE[resolved] = (mtime, catalog)
    return catalog


def sync_dcrust_syllabus(
    syllabus_dir: Path,
    *,
    download: bool = True,
    max_workers: int = 8,
    client: DcrustSyllabusClient | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> SyllabusCatalog:
    """Fetch all DCRUST syllabi, download files into branch/year folders, and save index.json."""
    syllabus_dir.mkdir(parents=True, exist_ok=True)
    client = client or DcrustSyllabusClient()
    entries = client.fetch_catalog()
    _assign_sorted_paths(entries)
    if progress_cb:
        progress_cb(f"Fetched {len(entries)} syllabus entries from {SYLLABUS_PAGE_URL}")

    old = load_syllabus_catalog(syllabus_dir)
    existing_by_url = {x.remote_url: x for x in old.entries} if old else {}

    to_download: list[SyllabusEntry] = []
    for e in entries:
        prev = existing_by_url.get(e.remote_url)
        target = syllabus_dir / e.local_relpath
        same_slot = prev is None or not prev.local_relpath or prev.local_relpath == e.local_relpath
        if same_slot and target.exists() and target.stat().st_size > 100:
            e.status = "downloaded"
            e.size_bytes = target.stat().st_size
            _hardlink_by_year(syllabus_dir, e)
        elif download:
            to_download.append(e)

    if download and to_download:
        done = 0
        total = len(to_download)
        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
            futs = {
                pool.submit(client.download_document, e, syllabus_dir / e.local_relpath): e
                for e in to_download
            }
            for fut in as_completed(futs):
                e = futs[fut]
                status, sz, actual_dest = fut.result()
                e.status = status
                e.size_bytes = sz
                if status == "downloaded":
                    e.local_relpath = str(actual_dest.relative_to(syllabus_dir))
                    e.file_type = actual_dest.suffix.lstrip(".").upper() or e.file_type
                    _hardlink_by_year(syllabus_dir, e)
                done += 1
                if progress_cb and (done % 25 == 0 or done == total):
                    progress_cb(f"Downloaded/checked {done}/{total} syllabus files...")

    entries.sort(key=lambda e: (e.department_id, e.year_id, -e.session_sort, e.title.lower()))
    catalog = SyllabusCatalog(
        source_url=SYLLABUS_PAGE_URL,
        updated_at=dt.datetime.now(tz=_IST).strftime("%Y-%m-%d %H:%M"),
        entries=entries,
    )
    save_syllabus_catalog(syllabus_dir, catalog)
    return catalog


def extract_syllabus_filters(query: str) -> tuple[str | None, str | None, str | None, list[str]]:
    """Extract (branch_id, year_id, degree, extra_keywords) from a natural-language query."""
    branch_id = next((bid for bid, pat in _BRANCH_QUERY_RULES if pat.search(query)), None)
    year_id = next((yid for yid, pat in _YEAR_QUERY_RULES if pat.search(query)), None)
    degree = next((deg for deg, pat in _DEGREE_QUERY_RULES if pat.search(query)), None)

    cleaned = _SYLLABUS_BOILERPLATE.sub(" ", query or "")
    cleaned = re.sub(r"[?!.,:;\"'()\[\]{}]+", " ", cleaned)
    tokens = [t.lower() for t in re.split(r"\s+", cleaned) if len(t) > 1]
    return branch_id, year_id, degree, tokens


def _score_syllabus_entry(
    entry: SyllabusEntry,
    branch_id: str | None,
    year_id: str | None,
    degree: str | None,
    tokens: list[str],
) -> float:
    score = 0.0
    hay = f"{entry.title} {entry.raw_text} {entry.department_label} {entry.degree} {entry.scheme or ''}".lower()

    if branch_id:
        if entry.department_id == branch_id:
            score += 60.0
        elif year_id == "1st" and entry.department_id == "common_1st" and degree in (None, "B.Tech"):
            score += 52.0
        else:
            return 0.0

    if degree:
        if entry.degree == degree or degree.lower() in entry.degree.lower():
            score += 22.0
        elif entry.degree != "Other":
            return 0.0

    if year_id:
        if entry.year_id == year_id:
            score += 45.0
        elif year_id in entry.covered_years:
            score += 36.0
        elif entry.year_id == "complete":
            score += 24.0
        else:
            score -= 25.0

    if tokens:
        hits = sum(1 for t in tokens if re.search(rf"\b{re.escape(t)}", hay))
        if not branch_id and not year_id and not degree and hits == 0:
            return 0.0
        score += (hits / max(len(tokens), 1)) * 18.0

    # Slight preference for locally downloaded files & newer revisions
    if entry.status == "downloaded":
        score += 4.0
    if entry.session_sort:
        score += min(4.0, max(0.0, (entry.session_sort - 201000) / 1000.0))
    return score


def search_syllabus(
    query: str,
    syllabus_dir: Path,
    *,
    catalog: SyllabusCatalog | None = None,
    limit: int = 20,
) -> SyllabusSearchResult:
    """Search DCRUST syllabus catalog by branch, year, degree, and keywords."""
    cat = catalog or load_syllabus_catalog(syllabus_dir)
    branch_id, year_id, degree, tokens = extract_syllabus_filters(query)
    branch_lbl = DEPARTMENTS.get(branch_id) if branch_id else None
    year_lbl = YEAR_LABELS.get(year_id) if year_id else None

    if cat is None or not cat.entries:
        return SyllabusSearchResult(
            raw_query=query,
            branch_id=branch_id,
            branch_label=branch_lbl,
            year_id=year_id,
            year_label=year_lbl,
            degree=degree,
            matches=[],
            catalog_total_entries=0,
            catalog_ready=False,
        )

    scored: list[tuple[float, SyllabusEntry]] = []
    for e in cat.entries:
        sc = _score_syllabus_entry(e, branch_id, year_id, degree, tokens)
        if sc >= 15.0:
            scored.append((sc, e))

    scored.sort(key=lambda pair: (-pair[0], -pair[1].session_sort, pair[1].year_id, pair[1].title.lower()))
    # When user specified year & we found exact/covered year matches, drop weaker mismatched-year fallback
    if year_id and scored and scored[0][0] >= 80.0:
        scored = [p for p in scored if p[0] >= 65.0]

    matches = [e for _, e in scored[:limit]]
    return SyllabusSearchResult(
        raw_query=query,
        branch_id=branch_id,
        branch_label=branch_lbl,
        year_id=year_id,
        year_label=year_lbl,
        degree=degree,
        matches=matches,
        catalog_total_entries=len(cat.entries),
        catalog_ready=True,
    )


def format_syllabus_markdown(result: SyllabusSearchResult, syllabus_dir: Path) -> str:
    """Format matched syllabi cleanly as Markdown sorted by relevance & year."""
    if not result.catalog_ready:
        return (
            f"No local DCRUST syllabus catalog found in `{syllabus_dir}` yet.\n\n"
            "Run `smriti syllabus sync` in your terminal to download and sort all university syllabi."
        )
    if not result.matches:
        return (
            f"No DCRUST syllabus matched `{result.raw_query}` across {result.catalog_total_entries} indexed documents.\n\n"
            "Try specifying a branch and year, e.g. `CSE 3rd year syllabus`, `B.Tech 1st year syllabus`, or `ECE 2nd year syllabus`."
        )

    filters = [x for x in (result.branch_label, result.degree, result.year_label) if x]
    filter_line = f"Filters: **{' · '.join(filters)}** · " if filters else ""
    lines = [
        f"### DCRUST University Syllabus · {len(result.matches)} document{'s' if len(result.matches) != 1 else ''} matched",
        f"{filter_line}Catalog: {result.catalog_total_entries} syllabi (`by_branch/` & `by_year/`)",
        "",
        "| Syllabus / Scheme | Branch | Program | Year | Type | Status | Portal |",
        "| :--- | :--- | :--- | :--- | :---: | :--- | :--- |",
    ]
    for e in result.matches:
        local_p = syllabus_dir / e.local_relpath if e.local_relpath else None
        is_local = bool(local_p and local_p.exists())
        status_txt = f"Saved ({max(1, e.size_bytes // 1024)} KB)" if is_local else (
            "Portal / Drive" if e.status == "portal_only" else "Link only"
        )
        lines.append(
            f"| **{e.title}** | {e.department_label} | {e.degree} | {e.year_label} | `{e.file_type}` | {status_txt} | [Open]({e.remote_url}) |"
        )
    return "\n".join(lines)


def syllabus_to_ui_props(result: SyllabusSearchResult, syllabus_dir: Path) -> dict:
    """Build JSON props for Chainlit `DcrustSyllabus.jsx` CustomElement."""
    items = []
    for e in result.matches:
        local_p = syllabus_dir / e.local_relpath if e.local_relpath else None
        is_local = bool(local_p and local_p.exists())
        items.append(
            {
                "title": e.title,
                "branch": e.department_label,
                "branchId": e.department_id,
                "degree": e.degree,
                "year": e.year_label,
                "yearId": e.year_id,
                "scheme": e.scheme,
                "sessionYear": e.session_year,
                "fileType": e.file_type,
                "localRelpath": e.local_relpath,
                "downloaded": is_local,
                "sizeKb": max(1, e.size_bytes // 1024) if is_local else 0,
                "remoteUrl": e.remote_url,
                "status": e.status,
            }
        )
    return {
        "query": result.raw_query,
        "branch": result.branch_label,
        "year": result.year_label,
        "degree": result.degree,
        "totalMatched": len(items),
        "catalogTotal": result.catalog_total_entries,
        "syllabusDir": str(syllabus_dir),
        "items": items,
    }


def format_syllabus_html(result: SyllabusSearchResult, syllabus_dir: Path) -> str:
    """Render a clean standalone HTML table for matched syllabi."""
    rows = []
    for e in result.matches:
        local_p = syllabus_dir / e.local_relpath if e.local_relpath else None
        is_local = bool(local_p and local_p.exists())
        local_col = f'<a href="{html_lib.escape(local_p.as_uri())}">Local {html_lib.escape(e.file_type)}</a>' if is_local and local_p else "—"
        rows.append(
            f"<tr><td><strong>{html_lib.escape(e.title)}</strong></td>"
            f"<td>{html_lib.escape(e.department_label)}</td>"
            f"<td>{html_lib.escape(e.degree)}</td>"
            f"<td>{html_lib.escape(e.year_label)}</td>"
            f"<td>{local_col}</td>"
            f'<td><a href="{html_lib.escape(e.remote_url)}" target="_blank" rel="noopener">Open ↗</a></td></tr>'
        )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>DCRUST Syllabus · {html_lib.escape(result.raw_query)}</title>
<style>
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:#f8fafc; color:#0f172a; margin:0; padding:1.5rem; }}
.wrap {{ max-width:1020px; margin:0 auto; }}
.card {{ background:#fff; border:1px solid #e2e8f0; border-radius:0.85rem; overflow:hidden; }}
table {{ width:100%; border-collapse:collapse; font-size:0.85rem; }}
th, td {{ padding:0.65rem 0.9rem; border-bottom:1px solid #f1f5f9; text-align:left; }}
th {{ background:#f8fafc; font-size:0.74rem; color:#64748b; text-transform:uppercase; }}
a {{ color:#4f46e5; text-decoration:none; font-weight:600; }}
</style></head><body><div class="wrap">
<h2>DCRUST University Syllabus</h2>
<p>Query: <strong>{html_lib.escape(result.raw_query)}</strong> · {len(result.matches)} matched</p>
<div class="card"><table><thead><tr><th>Title</th><th>Branch</th><th>Program</th><th>Year</th><th>Local</th><th>Portal</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div></div></body></html>"""
