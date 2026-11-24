"""The study library as Semester → Course → Document → Topic (PRD U1)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_WORDS_TO_NUM = {
    "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4, "fifth": 5, "5th": 5, "sixth": 6, "6th": 6,
    "seventh": 7, "7th": 7, "eighth": 8, "8th": 8,
}
_SEMESTER = re.compile(r"(?:^|[^a-z0-9])sem(?:ester)?[\s_-]*0?(\d{1,2})(?![0-9])", re.IGNORECASE)
_WORD_SEMESTER_1 = re.compile(r"\b(" + "|".join(_WORDS_TO_NUM) + r")[\s_-]*sem(?:ester)?\b", re.IGNORECASE)
_WORD_SEMESTER_2 = re.compile(r"\bsem(?:ester)?[\s_-]*(" + "|".join(_WORDS_TO_NUM) + r")\b", re.IGNORECASE)


def detect_semester(text: str) -> int | None:
    """'my sem 5 notes', 'semester-05/os.pdf', 'first_sem_dmc', 'Fourth Semester' -> semester number."""
    m = _SEMESTER.search(text)
    if m:
        return int(m.group(1))
    m = _WORD_SEMESTER_1.search(text)
    if m:
        return _WORDS_TO_NUM[m.group(1).lower()]
    m = _WORD_SEMESTER_2.search(text)
    if m:
        return _WORDS_TO_NUM[m.group(1).lower()]
    return None


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
