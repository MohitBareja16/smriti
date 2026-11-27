"""Safe file path resolution and attachment metadata helpers for Smriti FastAPI."""

from __future__ import annotations

import mimetypes
import urllib.parse
from pathlib import Path

from smriti.app import App


def _allowed_roots(app: App) -> list[Path]:
    roots = [
        app.settings.pyq_dir,
        app.settings.syllabus_dir,
        app.settings.data_dir / "exports",
        app.settings.data_dir / "documents",
    ]
    out: list[Path] = []
    for r in roots:
        try:
            out.append(r.resolve())
        except OSError:
            continue
    return out


def is_allowed_file_path(candidate: Path, app: App) -> bool:
    """True only when `candidate` resolves inside approved app directories or a non-sensitive doc."""
    try:
        resolved = candidate.expanduser().resolve()
    except OSError:
        return False
    if not resolved.is_file():
        return False

    for root in _allowed_roots(app):
        if resolved.is_relative_to(root):
            return True

    for doc in app.db.list_documents():
        if doc["sensitive"] or not doc["path"]:
            continue
        p = Path(doc["path"])
        if p.exists():
            try:
                if resolved == p.resolve():
                    return True
            except OSError:
                continue
    return False


def file_view_url(path: str | Path) -> str:
    return f"/api/files/raw?path={urllib.parse.quote(str(path), safe='')}"


def serialize_attachments(paths: list[str], app: App) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for raw in paths:
        if not raw or raw in seen:
            continue
        seen.add(raw)
        p = Path(raw)
        if not is_allowed_file_path(p, app):
            continue
        size = p.stat().st_size if p.exists() else 0
        items.append(
            {
                "name": p.name,
                "path": str(p),
                "url": file_view_url(p),
                "ext": p.suffix.lower().lstrip("."),
                "sizeBytes": size,
            }
        )
    return items


def media_type_for(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return "application/pdf"
    if ext == ".html":
        return "text/html; charset=utf-8"
    if ext == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if ext == ".doc":
        return "application/msword"
    if ext in {".md", ".txt"}:
        return "text/plain; charset=utf-8"
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"
