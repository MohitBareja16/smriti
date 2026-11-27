"""Turn files into a list of (page_number, text). Page numbers are kept for citations.

Markdown/text files can mark page breaks with a line containing only `<!-- page -->` or a form feed.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

_log = logging.getLogger(__name__)

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
    import shutil
    import subprocess
    import tempfile

    from pypdf import PdfReader

    reader = PdfReader(str(path))
    has_tesseract = shutil.which("tesseract") is not None
    out = []
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        # Scanned PDFs have no text layer: run OCR fallback if tesseract is available
        if len(text) < 20 and has_tesseract:
            ocr_parts = []
            try:
                images = list(page.images)
            except (ImportError, KeyError, OSError, ValueError, TypeError):
                _log.debug("Image extraction skipped for %s page %s", path.name, i, exc_info=True)
                images = []
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            for img in images:
                tpath: str | None = None
                try:
                    suffix = Path(getattr(img, "name", "") or "page.png").suffix or ".png"
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                        tmp.write(img.data)
                        tpath = tmp.name
                    res = subprocess.run(
                        ["tesseract", tpath, "stdout"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=False,
                        creationflags=creationflags,
                    )
                    if res.stdout.strip():
                        ocr_parts.append(res.stdout.strip())
                except (OSError, subprocess.SubprocessError, ValueError):
                    _log.debug("OCR fallback skipped for %s page %s", path.name, i, exc_info=True)
                finally:
                    if tpath:
                        try:
                            Path(tpath).unlink(missing_ok=True)
                        except OSError:
                            _log.debug("Failed to delete temporary OCR file %s", tpath, exc_info=True)
            if ocr_parts:
                text = "\n".join(ocr_parts)
        if text:
            out.append((i, text))
    return out


def _parse_docx(path: Path) -> list[tuple[int, str]]:
    try:
        import docx  # python-docx
    except ImportError as exc:
        raise UnsupportedFileError("Install the 'docx' extra: pip install 'smriti[docx]'") from exc
    text = "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    return [(1, text.strip())] if text.strip() else []
