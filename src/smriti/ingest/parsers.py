"""Turn files into a list of (page_number, text). Page numbers are kept for citations.

Markdown/text files can mark page breaks with a line containing only `<!-- page -->` or a form feed.
"""

from __future__ import annotations

import re
from pathlib import Path

PAGE_MARKER = re.compile(r"^\s*<!--\s*page\s*-->\s*$|\f", re.MULTILINE)
SUPPORTED = {".pdf", ".md", ".txt", ".docx"}


class UnsupportedFileError(ValueError):
    pass


def parse(path: Path) -> list[tuple[int, str]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(path)
    if suffix in {".md", ".txt"}:
        return parse_text(path.read_text(encoding="utf-8", errors="replace"))
    if suffix == ".docx":
        return _parse_docx(path)
    raise UnsupportedFileError(f"Unsupported file type: {suffix} (supported: {', '.join(sorted(SUPPORTED))})")


def parse_text(text: str) -> list[tuple[int, str]]:
    pages = PAGE_MARKER.split(text)
    return [(i, p.strip()) for i, p in enumerate(pages, 1) if p.strip()]


def _parse_pdf(path: Path) -> list[tuple[int, str]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [(i, (page.extract_text() or "").strip()) for i, page in enumerate(reader.pages, 1)]
    # Scanned PDFs have no text layer; OCR (Docling/Tesseract) is a planned module.
    return [(i, t) for i, t in pages if t]


def _parse_docx(path: Path) -> list[tuple[int, str]]:
    try:
        import docx  # python-docx
    except ImportError as exc:
        raise UnsupportedFileError("Install the 'docx' extra: pip install 'smriti[docx]'") from exc
    text = "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    return [(1, text.strip())] if text.strip() else []
