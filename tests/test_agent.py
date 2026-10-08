from smriti.agent.system2 import TOOL_PLANS, System2Agent, top_facts
from smriti.observability import Tracer


def _tools(answer):
    return [s.name for s in answer.trace if s.name.startswith("s2.tool.")]


def test_agent_is_a_langgraph_state_machine(demo_app):
    o = demo_app.orchestrator
    agent = System2Agent(demo_app.db, o.reasoner, o.engine)
    assert set(agent.graph.get_graph().nodes) >= {"plan", "act", "broaden", "tools", "guard", "answer"}


def test_escalated_fact_question_uses_facts_and_vault(demo_app):
    a = demo_app.orchestrator.handle("When is my DBMS exam?", mode="agent")
    assert _tools(a)[:2] == ["s2.tool.vault_search", "s2.tool.facts_lookup"]
    assert "10 December 2026" in a.text and any(c.startswith("exam_timetable") for c in a.citations)


def test_study_questions_search_only_the_library(demo_app):
    a = demo_app.orchestrator.handle("Explain the four conditions for deadlock from my OS notes")
    searches = [s.detail for s in a.trace if s.name == "s2.tool.library_search"]
    assert searches and "kind=library" in searches[0]
    assert not any(c.startswith(("marksheet", "exam_timetable", "certificates")) for c in a.citations)


def test_escalated_fetch_uses_get_document(demo_app):
    a = demo_app.orchestrator.handle("Give me my AWS certificate", mode="agent")
    assert "s2.tool.get_document" in _tools(a)


def test_tools_can_be_switched_off_for_ablation(demo_app):
    demo_app.orchestrator.settings.agent_tools = False
    a = demo_app.orchestrator.handle("When is my DBMS exam?", mode="agent")
    assert _tools(a) and set(_tools(a)) == {"s2.tool.search"}


def test_top_facts_skip_conflicting_numbers(demo_app):
    facts = top_facts("What was my SGPA in semester 9?", demo_app.db.all_facts())
    assert all("Semester 4" not in f.attribute for f in facts)
    assert set(TOOL_PLANS) >= {"fact_lookup", "fetch_doc", "explain", "compare", "exam_prep", "connect", "other"}


def test_broadening_happens_when_scope_is_empty(demo_app):
    o = demo_app.orchestrator
    agent = System2Agent(demo_app.db, o.reasoner, o.engine)
    t = Tracer()
    agent.run("Explain paging from my semester 3 notes", t, intent="explain")
    names = [s.name for s in t.steps]
    assert names.count("s2.tool.library_search") == 1 and "s2.replan" in names and "s2.tool.search" in names
