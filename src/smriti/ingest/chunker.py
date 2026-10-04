"""Page-aware chunking: chunks never cross a page boundary, so every chunk can cite its page."""

from __future__ import annotations

import re

_PARAGRAPH = re.compile(r"\n\s*\n")


def chunk_pages(pages: list[tuple[int, str]], max_chars: int = 900) -> list[tuple[int, str]]:
    chunks: list[tuple[int, str]] = []
    for page, text in pages:
        buf = ""
        for para in (p.strip() for p in _PARAGRAPH.split(text)):
            if not para:
                continue
            if buf and len(buf) + len(para) + 2 > max_chars:
                chunks.append((page, buf))
                buf = ""
            while len(para) > max_chars:  # very long paragraph: hard split on a sentence/space boundary
                cut = max(para.rfind(". ", 0, max_chars), para.rfind(" ", 0, max_chars))
                cut = cut + 1 if cut > 0 else max_chars
                chunks.append((page, para[:cut].strip()))
                para = para[cut:].strip()
            buf = f"{buf}\n\n{para}" if buf else para
        if buf:
            chunks.append((page, buf))
    return chunks
