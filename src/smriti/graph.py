"""A small, deterministic knowledge graph of the student's library (issue #17, PRD U8).

Built from what Smriti already knows, with no LLM, so it is reproducible and works offline:

    Semester –has_course→ Course –has_document→ Document –covers→ Topic
    Course –teaches→ Skill        Project –uses→ Skill        Certification –proves→ Skill
    Exam –for→ Course             Document –mentions→ Skill   (other documents)

Skills come from an extendable vocabulary (SKILLS). Every edge keeps the document and page it came
from, so answers built on the graph still cite pages. `lookup()` turns a connection question
("Which skills from my DBMS course have I used in projects?") into short, cited facts that the
System-2 agent uses as evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from smriti.storage import Database

# canonical skill -> regex of ways it is written (case-insensitive)
SKILLS: dict[str, str] = {
    "Python": r"\bpython\b",
    "FastAPI": r"\bfastapi\b",
    "SQL databases": r"\b(sql|postgresql|postgres|mysql|sqlite)\b",
    "normalization": r"\b(normali[sz]\w*|normal form|[123]nf|bcnf)\b",
    # not the verb ("the page number indexes the page table"): only database-index phrasings
    "indexing": r"(\bindexing\b|\b(an|the|database|hash|secondary|primary) index(es)?\b|\bb\+ ?trees?)",
    "transactions": r"\b(transactions?|acid|atomicity|durability)\b",
    "concurrency": r"\b(threads?|multithread\w*|locks?|concurren\w*|race conditions?)\b",
    "CPU scheduling": r"\b(scheduling|scheduler|round robin|fcfs|sjf)\b",
    "memory management": r"\b(paging|page tables?|segmentation|tlb)\b",
    "deadlocks": r"\b(deadlocks?|banker'?s algorithm)\b",
    "AWS": r"\b(aws|amazon web services)\b",
    "machine learning": r"\b(machine learning|ml)\b",
    "web development": r"\b(web app\w*|websites?|flask|django|react)\b",
}
_SKILL_RE = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in SKILLS.items()}

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    UNIQUE(type, name)
);
CREATE TABLE IF NOT EXISTS edges (
    src INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    rel TEXT NOT NULL,
    dst INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    doc_title TEXT NOT NULL,
    page INTEGER NOT NULL,
    UNIQUE(src, rel, dst, doc_title, page)
);
"""

TYPE_WORDS = {
    "Project": r"\bprojects?\b",
    "Certification": r"\b(certificates?|certifications?|certified)\b",
    "Exam": r"\bexams?\b",
    "Skill": r"\bskills?\b",
    "Topic": r"\btopics?\b",
}


def find_skills(text: str) -> list[str]:
    return [name for name, rx in _SKILL_RE.items() if rx.search(text)]


@dataclass
class GraphFact:
    text: str
    refs: list[str] = field(default_factory=list)


class KnowledgeGraph:
    def __init__(self, db: Database):
        self.db = db
        self.conn = db.conn
        self.conn.executescript(SCHEMA)

    # ---- build -------------------------------------------------------------------------------
    def _entity(self, type_: str, name: str) -> int:
        self.conn.execute("INSERT OR IGNORE INTO entities (type, name) VALUES (?, ?)", (type_, name))
        return self.conn.execute("SELECT id FROM entities WHERE type = ? AND name = ?", (type_, name)).fetchone()[0]

    def _edge(self, src: int, rel: str, dst: int, doc: str, page: int) -> None:
        self.conn.execute("INSERT OR IGNORE INTO edges (src, rel, dst, doc_title, page) VALUES (?, ?, ?, ?, ?)",
                          (src, rel, dst, doc, page))

    def rebuild(self) -> dict[str, int]:
        """Recompute the whole graph from documents, chunks and facts. Returns entity counts per type."""
        self.conn.execute("DELETE FROM edges")
        self.conn.execute("DELETE FROM entities")
        rows = self.conn.execute(
            "SELECT c.page, c.text, c.topic, d.title, d.course, d.semester, d.doc_type FROM chunks c "
            "JOIN documents d ON d.id = c.doc_id ORDER BY c.id").fetchall()
        for r in rows:
            doc = self._entity("Document", r["title"])
            course = self._entity("Course", r["course"]) if r["course"] else None
            if course:
                self._edge(course, "has_document", doc, r["title"], r["page"])
            if r["semester"] is not None:
                sem = self._entity("Semester", f"Semester {r['semester']}")
                self._edge(sem, "has_course" if course else "has_document", course or doc, r["title"], r["page"])
            if r["topic"]:
                topic = self._entity("Topic", r["topic"])
                self._edge(doc, "covers", topic, r["title"], r["page"])
                if course:
                    self._edge(course, "covers", topic, r["title"], r["page"])
            skills = find_skills(f"{r['topic'] or ''}\n{r['text']}")
            if not skills:
                continue
            if r["doc_type"] == "project" and r["topic"]:
                owner, rel = self._entity("Project", r["topic"]), "uses"
            elif r["doc_type"] == "certificate" and r["topic"]:
                owner, rel = self._entity("Certification", r["topic"]), "proves"
            elif course:
                owner, rel = course, "teaches"
            else:
                owner, rel = doc, "mentions"
            for s in skills:
                self._edge(owner, rel, self._entity("Skill", s), r["title"], r["page"])
        courses = {r["name"]: r["id"] for r in self.conn.execute("SELECT id, name FROM entities WHERE type='Course'")}
        for f in self.db.all_facts():
            if "exam" not in f.attribute.lower():
                continue
            exam = self._entity("Exam", f.attribute)
            for name, cid in courses.items():
                if re.search(rf"\b{re.escape(name)}\b", f.attribute, re.IGNORECASE):
                    self._edge(exam, "for", cid, f.doc_title, f.page)
        self.conn.commit()
        return self.counts()

    # ---- read --------------------------------------------------------------------------------
    def counts(self) -> dict[str, int]:
        return {r["type"]: r["n"] for r in self.conn.execute(
            "SELECT type, COUNT(*) AS n FROM entities GROUP BY type ORDER BY type")}

    def names(self, type_: str) -> list[str]:
        return [r["name"] for r in self.conn.execute("SELECT name FROM entities WHERE type = ? ORDER BY name",
                                                     (type_,))]

    def related(self, src_type: str, rel: str, src_name: str | None = None) -> dict[str, dict[str, set[str]]]:
        """{source name: {target name: {refs}}} for edges of one relation (optionally one source)."""
        sql = ("SELECT s.name AS src, t.name AS dst, e.doc_title, e.page FROM edges e "
               "JOIN entities s ON s.id = e.src JOIN entities t ON t.id = e.dst WHERE s.type = ? AND e.rel = ?")
        params: list = [src_type, rel]
        if src_name:
            sql += " AND lower(s.name) = lower(?)"
            params.append(src_name)
        out: dict[str, dict[str, set[str]]] = {}
        for r in self.conn.execute(sql, params):
            out.setdefault(r["src"], {}).setdefault(r["dst"], set()).add(f"{r['doc_title']} p.{r['page']}")
        return out

    def neighbors(self, name: str) -> list[tuple[str, str, str, str]]:
        """(direction, relation, other entity "Type: name", ref) for an entity name, both directions."""
        q = ("SELECT 'out' AS d, e.rel, t.type || ': ' || t.name AS other, e.doc_title || ' p.' || e.page AS ref "
             "FROM edges e JOIN entities s ON s.id = e.src JOIN entities t ON t.id = e.dst "
             "WHERE lower(s.name) = lower(?) UNION "
             "SELECT 'in', e.rel, s.type || ': ' || s.name, e.doc_title || ' p.' || e.page "
             "FROM edges e JOIN entities s ON s.id = e.src JOIN entities t ON t.id = e.dst "
             "WHERE lower(t.name) = lower(?) ORDER BY 1, 2, 3")
        return [tuple(r) for r in self.conn.execute(q, (name, name))]

    # ---- answer connection questions --------------------------------------------------------
    @staticmethod
    def _merge(*maps: dict[str, dict[str, set[str]]]) -> dict[str, set[str]]:
        merged: dict[str, set[str]] = {}
        for m in maps:
            for targets in m.values():
                for t, refs in targets.items():
                    merged.setdefault(t, set()).update(refs)
        return merged

    def _owners(self, src_type: str, rel: str) -> dict[str, list[str]]:
        """{skill: [owners]} e.g. which projects use each skill."""
        out: dict[str, list[str]] = {}
        for owner, targets in self.related(src_type, rel).items():
            for skill in targets:
                out.setdefault(skill, []).append(owner)
        return out

    def lookup(self, question: str) -> list[GraphFact]:
        q = question.lower()
        courses = [c for c in self.names("Course") if re.search(rf"\b{re.escape(c.lower())}\b", q)]
        types = {t for t, rx in TYPE_WORDS.items() if re.search(rx, q)}
        skills = [s for s in self.names("Skill")
                  if _SKILL_RE.get(s, re.compile(re.escape(s), re.IGNORECASE)).search(q)]
        facts: list[GraphFact] = []

        uses = self.related("Project", "uses")
        if "Project" in types:
            project_skills = self._merge(uses)
            owners = self._owners("Project", "uses")
            sources = [(f"the {c} course", self.related("Course", "teaches", c)) for c in courses]
            if "Certification" in types:
                sources.append(("your certificates", self.related("Certification", "proves")))
            for label, taught in sources:
                shared = sorted(set(self._merge(taught)) & set(project_skills))
                if shared:
                    refs = sorted({r for s in shared for r in self._merge(taught)[s] | project_skills[s]})
                    parts = [f"{s} (in {', '.join(sorted(owners[s]))})" for s in shared]
                    facts.append(GraphFact(f"Skills from {label} that you used in your projects: "
                                           f"{'; '.join(parts)}.", refs))
                else:
                    facts.append(GraphFact(f"No skill from {label} appears in your project write-ups."))
        if "Exam" in types:
            for exam, targets in self.related("Exam", "for").items():
                if not courses or any(c in targets for c in courses):
                    value = next((f.value for f in self.db.all_facts() if f.attribute == exam), "")
                    refs = sorted({r for v in targets.values() for r in v})
                    facts.append(GraphFact(f"{exam}: {value}.", refs))
        for c in courses:
            if "Topic" in types and "Project" not in types:
                topics = self._merge(self.related("Course", "covers", c))
                facts.append(GraphFact(f"Topics covered in {c}: {', '.join(sorted(topics))}.",
                                       sorted({r for v in topics.values() for r in v})[:6]))
            if "Skill" in types and "Project" not in types:
                taught = self._merge(self.related("Course", "teaches", c))
                facts.append(GraphFact(f"Skills taught in {c}: {', '.join(sorted(taught))}.",
                                       sorted({r for v in taught.values() for r in v})[:6]))
        for s in skills:
            where, refs = [], set()
            for type_, rel, label in [("Course", "teaches", "taught in"), ("Project", "uses", "used in"),
                                      ("Certification", "proves", "proven by")]:
                owners = {o: t[s] for o, t in self.related(type_, rel).items() if s in t}
                if owners:
                    where.append(f"{label} {', '.join(sorted(owners))}")
                    refs |= {r for rs in owners.values() for r in rs}
            if where:
                facts.append(GraphFact(f"{s} is {'; '.join(where)}.", sorted(refs)))
        return facts
