import pytest

from smriti.decision import RulesEngine
from smriti.graph import KnowledgeGraph, find_skills


def test_skill_vocabulary_ignores_the_verb_index():
    assert "indexing" in find_skills("A B+ tree index on the event date")
    assert "indexing" not in find_skills("The page number indexes the page table.")
    assert set(find_skills("Built with Python and FastAPI on AWS")) == {"Python", "FastAPI", "AWS"}


def test_graph_is_built_on_ingest(demo_app):
    g = KnowledgeGraph(demo_app.db)
    counts = g.counts()
    assert counts["Course"] == 2 and counts["Project"] == 2 and counts["Exam"] >= 2
    assert {"indexing", "normalization", "transactions"} <= set(g._merge(g.related("Course", "teaches", "DBMS")))
    assert "indexing" not in g._merge(g.related("Course", "teaches", "OS"))
    assert "AWS" in g._merge(g.related("Certification", "proves"))


def test_lookup_intersects_course_and_project_skills_with_citations(demo_app):
    facts = KnowledgeGraph(demo_app.db).lookup("Which skills from my DBMS course have I used in projects?")
    text = " ".join(f.text for f in facts)
    assert "normalization" in text and "indexing" in text and "Campus Events Portal" in text
    refs = {r for f in facts for r in f.refs}
    assert any(r.startswith("dbms_notes") for r in refs) and any(r.startswith("projects") for r in refs)


def test_lookup_certificates_and_exams(demo_app):
    g = KnowledgeGraph(demo_app.db)
    assert "AWS" in " ".join(f.text for f in g.lookup("Which of my certificates relate to my projects?"))
    assert "10 December 2026" in " ".join(f.text for f in g.lookup("When are my DBMS exams?"))


@pytest.mark.parametrize("question", [
    "Which skills from my DBMS course have I used in projects?",
    "Which of my certificates relate to my projects?",
    "Where have I used transactions?",
])
def test_router_sends_connection_questions_to_connect(question):
    assert RulesEngine().route(question).label == "connect"


def test_agent_uses_graph_for_connect_questions(demo_app):
    a = demo_app.orchestrator.handle("Which skills from my DBMS course have I used in projects?")
    assert a.intent == "connect" and any(s.name == "s2.tool.graph_lookup" for s in a.trace)
    assert "normalization" in a.text and any(c.startswith("knowledge graph") for c in a.citations)


def test_graph_rebuild_is_deterministic(demo_app):
    g = KnowledgeGraph(demo_app.db)
    first = g.neighbors("DBMS")
    g.rebuild()
    assert g.neighbors("DBMS") == first
