"""Document-type classification. Keyword baseline; a System-1 engine can replace it later."""

from __future__ import annotations

DOC_TYPES: dict[str, tuple[str, ...]] = {
    "marksheet": ("marksheet", "grade card", "sgpa", "cgpa", "result"),
    "certificate": ("certificate", "certified", "certification", "credential id"),
    "timetable": ("timetable", "date sheet", "datesheet", "exam schedule", "end-term"),
    "past_paper": ("question paper", "past paper", "previous year", "attempt any", "max. marks"),
    "syllabus": ("syllabus", "course outcomes", "unit i", "unit 1:"),
    "project": ("project", "built with", "deployed", "github", "repository"),
    "book": ("chapter", "isbn", "edition", "preface"),
    "notes": ("notes", "lecture", "unit"),
}


def classify_document(title: str, text: str) -> str:
    haystack = f"{title}\n{text[:3000]}".lower()
    scores = {t: sum(haystack.count(k) for k in kws) for t, kws in DOC_TYPES.items()}
    # The file name is a strong signal: weight it extra.
    for t, kws in DOC_TYPES.items():
        scores[t] += 3 * sum(k.replace(" ", "_") in title.lower() or k in title.lower() for k in kws)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"
