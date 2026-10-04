"""Small text helpers shared by System-1 components."""

from __future__ import annotations

from parag.storage import content_tokens

GENERIC = frozenset({"notes", "note", "book", "books", "slides", "chapter", "page", "pdf", "document",
                     "documents", "file", "course", "get", "got", "find", "need"})


SYNONYMS = {"sem": "semester", "exams": "exam", "dob": "birth", "gpa": "cgpa"}


def norm(token: str) -> str:
    """Crude stemming: compare the first 5 characters (expire/expiry, certificate/certified)."""
    token = SYNONYMS.get(token, token)
    return token[:5] if len(token) > 5 else token


def norm_set(text: str, drop_generic: bool = False) -> set[str]:
    toks = content_tokens(text)
    if drop_generic:
        toks = [t for t in toks if t not in GENERIC]
    return {norm(t) for t in toks}


def overlap_f1(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    common = len(a & b)
    if not common:
        return 0.0
    precision, recall = common / len(b), common / len(a)
    return 2 * precision * recall / (precision + recall)
