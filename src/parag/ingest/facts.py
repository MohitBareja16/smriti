"""Extract structured facts ("DBMS exam: 10 Dec 2026") from personal documents.

Facts power the System-1 fast path: simple lookups are answered from this table without an LLM.
"""

from __future__ import annotations

import re

_LINE = re.compile(r"^\s*(?:[-*•]\s*)?(?P<key>[A-Za-z][\w ()/&.'-]{1,60}?)\s*[:=]\s*(?P<value>\S.{0,200})$")
_MD = re.compile(r"[*_`#>]")


def extract_facts(pages: list[tuple[int, str]]) -> list[tuple[int, str, str]]:
    facts: list[tuple[int, str, str]] = []
    for page, text in pages:
        for raw in text.splitlines():
            line = _MD.sub("", raw).strip()
            m = _LINE.match(line)
            if not m:
                continue
            key, value = m.group("key").strip(), m.group("value").strip()
            if key.lower().startswith(("http", "note")) or len(key.split()) > 8:
                continue
            facts.append((page, key, value))
    return facts
