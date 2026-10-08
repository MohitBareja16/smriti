"""Page-aware, topic-aware chunking.

Chunks never cross a page boundary (so every chunk can cite its page) and never cross a heading
(so every chunk belongs to one topic, e.g. "Deadlock", for the Semester → Course → Topic library).
"""

from __future__ import annotations

import re

_PARAGRAPH = re.compile(r"\n\s*\n")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def heading(paragraph: str) -> tuple[int, str] | None:
    """('## Deadlock') -> (2, 'Deadlock'); None if the paragraph doesn't start with a Markdown heading."""
    m = _HEADING.match(paragraph.splitlines()[0]) if paragraph else None
    return (len(m.group(1)), m.group(2).strip()) if m else None


def chunk_with_topics(pages: list[tuple[int, str]], max_chars: int = 900) -> list[tuple[int, str, str | None]]:
    """[(page, text, topic)]. The topic is the latest level-2+ heading (or the title if none yet)."""
    chunks: list[tuple[int, str, str | None]] = []
    title: str | None = None
    section: str | None = None
    for page, text in pages:
        buf = ""
        for para in (p.strip() for p in _PARAGRAPH.split(text)):
            if not para:
                continue
            h = heading(para)
            if h:
                if buf:  # a new topic starts: close the current chunk
                    chunks.append((page, buf, section or title))
                    buf = ""
                level, name = h
                if level == 1:
                    title, section = name, None
                else:
                    section = name
            topic = section or title
            if buf and len(buf) + len(para) + 2 > max_chars:
                chunks.append((page, buf, topic))
                buf = ""
            while len(para) > max_chars:  # very long paragraph: hard split on a sentence/space boundary
                cut = max(para.rfind(". ", 0, max_chars), para.rfind(" ", 0, max_chars))
                cut = cut + 1 if cut > 0 else max_chars
                chunks.append((page, para[:cut].strip(), topic))
                para = para[cut:].strip()
            buf = f"{buf}\n\n{para}" if buf else para
        if buf:
            chunks.append((page, buf, section or title))
    return chunks


def chunk_pages(pages: list[tuple[int, str]], max_chars: int = 900) -> list[tuple[int, str]]:
    """[(page, text)], for callers that don't need topics."""
    return [(page, text) for page, text, _ in chunk_with_topics(pages, max_chars)]
