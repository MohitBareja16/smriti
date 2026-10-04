"""Lightweight PII detection and redaction (regex-based, zero dependencies).

Microsoft Presidio can replace this later behind the same functions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "aadhaar": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "pan": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    "phone": re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)"),
    "card_number": re.compile(r"\b(?:\d{4}[\s-]){3}\d{4}\b"),
    "passport": re.compile(r"\b[A-Z]\d{7}\b"),
}

# Words in a question that mean the user is explicitly asking for that PII type.
PII_REQUEST_WORDS: dict[str, tuple[str, ...]] = {
    "email": ("email", "e-mail", "mail id"),
    "aadhaar": ("aadhaar", "aadhar", "uid"),
    "pan": ("pan",),
    "phone": ("phone", "mobile", "contact number"),
    "card_number": ("card number",),
    "passport": ("passport",),
}


@dataclass
class PIIMatch:
    kind: str
    value: str
    start: int
    end: int


def find_pii(text: str) -> list[PIIMatch]:
    matches: list[PIIMatch] = []
    taken: list[tuple[int, int]] = []
    for kind, pattern in PII_PATTERNS.items():
        for m in pattern.finditer(text):
            if any(m.start() < e and m.end() > s for s, e in taken):
                continue  # already covered by an earlier, more specific pattern
            matches.append(PIIMatch(kind, m.group(0), m.start(), m.end()))
            taken.append((m.start(), m.end()))
    return sorted(matches, key=lambda m: m.start)


def redact(text: str, keep: set[str] | None = None) -> str:
    """Replace PII with [REDACTED:<kind>], except kinds listed in `keep`."""
    keep = keep or set()
    out, last = [], 0
    for m in find_pii(text):
        if m.kind in keep:
            continue
        out.append(text[last:m.start])
        out.append(f"[REDACTED:{m.kind}]")
        last = m.end
    out.append(text[last:])
    return "".join(out)


def requested_pii_kinds(question: str) -> set[str]:
    q = question.lower()
    return {kind for kind, words in PII_REQUEST_WORDS.items() if any(w in q for w in words)}
