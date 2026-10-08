"""The study library as Semester → Course → Document → Topic (PRD U1)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SEMESTER = re.compile(r"(?:^|[^a-z0-9])sem(?:ester)?[\s_-]*0?(\d{1,2})(?![0-9])", re.IGNORECASE)


def detect_semester(text: str) -> int | None:
    """'my sem 5 notes', 'semester-05/os.pdf', 'Sem4' -> the semester number; None if absent."""
    m = _SEMESTER.search(text)
    return int(m.group(1)) if m else None


@dataclass
class DocumentNode:
    title: str
    kind: str
    doc_type: str
    topics: list[str] = field(default_factory=list)


def build_tree(rows) -> dict:
    """{semester|None: {course|None: {title: DocumentNode}}} from Database.library_tree() rows."""
    tree: dict = {}
    for r in rows:
        doc = tree.setdefault(r["semester"], {}).setdefault(r["course"], {}).setdefault(
            r["title"], DocumentNode(r["title"], r["kind"], r["doc_type"]))
        if r["topic"] and r["topic"] not in doc.topics:
            doc.topics.append(r["topic"])
    return tree


def render_tree(tree: dict, show_topics: bool = True) -> str:
    lines = []
    for semester, courses in tree.items():
        lines.append(f"Semester {semester}" if semester is not None else "No semester")
        for course, docs in courses.items():
            lines.append(f"  {course or 'No course'}")
            for doc in docs.values():
                lock = " 🔒" if doc.kind == "personal" else ""
                lines.append(f"    {doc.title} ({doc.doc_type}){lock}")
                if show_topics and doc.kind != "personal":
                    lines += [f"      · {t}" for t in doc.topics]
    return "\n".join(lines)
