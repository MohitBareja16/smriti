from __future__ import annotations

import time

from smriti.agent.system2 import System2Agent
from smriti.config import Settings
from smriti.llm.extractive import contextualize_followup, needs_contextualization
from smriti.storage import Database


def test_threads_and_sliding_context_window(tmp_path):
    db = Database(tmp_path / "smriti.db")
    tid = db.create_thread()
    row = db.get_thread(tid)
    assert row is not None and row["title"] == "New Chat"

    # First user message auto-titles the thread
    db.add_chat_message(tid, "user", "Explain deadlock in operating systems")
    db.add_chat_message(tid, "assistant", "Deadlock happens when processes wait on each other indefinitely.")
    assert db.get_thread(tid)["title"].startswith("Explain deadlock")

    # Add several more turns and verify sliding window caps by max_turns
    for i in range(5):
        db.add_chat_message(tid, "user", f"Follow-up question {i}")
        db.add_chat_message(tid, "assistant", f"Answer {i}")

    win = db.recent_history(tid, max_turns=2, max_chars=5000)
    assert len(win) == 4
    assert win[0]["content"] == "Follow-up question 3"
    assert win[-1]["content"] == "Answer 4"

    # Verify char budget pruning keeps newest turns
    char_win = db.recent_history(tid, max_turns=6, max_chars=45)
    assert len(char_win) < 12
    assert char_win[-1]["content"] == "Answer 4"

    # Thread management: rename, list order, delete cascade
    tid2 = db.create_thread("Second thread")
    time.sleep(0.01)
    assert db.rename_thread(tid2, "Renamed Chat")
    threads = db.list_threads()
    assert threads[0]["id"] == tid2 and threads[0]["title"] == "Renamed Chat"
    assert db.delete_thread(tid)
    assert db.thread_messages(tid) == []


def test_followup_contextualizer_resolves_domains_and_pronouns():
    # Syllabus branch switch
    h_syl = [
        {"role": "user", "content": "Give me CSE 3rd year syllabus"},
        {"role": "assistant", "content": "Here are 8 CSE 3rd year syllabi."},
    ]
    rewritten_syl = contextualize_followup("What about ECE?", h_syl)
    assert "ece" in rewritten_syl.lower() and "3rd" in rewritten_syl.lower() and "syllabus" in rewritten_syl.lower()

    # PYQ subject switch
    h_pyq = [
        {"role": "user", "content": "Show PYQs for CSE302C"},
        {"role": "assistant", "content": "Found 3 PYQs for Compiler Design."},
    ]
    rewritten_pyq = contextualize_followup("What about Soft Computing?", h_pyq)
    assert "pyq" in rewritten_pyq.lower() and "soft computing" in rewritten_pyq.lower()

    # Pronoun topic resolution
    h_topic = [
        {"role": "user", "content": "Explain deadlock from my OS notes"},
        {"role": "assistant", "content": "Deadlock occurs when threads wait in a cycle."},
    ]
    rewritten_topic = contextualize_followup("What are its four conditions?", h_topic)
    assert "deadlock" in rewritten_topic.lower()

    # Standalone questions are left untouched
    assert not needs_contextualization("When is my DBMS exam?")
    assert contextualize_followup("When is my DBMS exam?", h_topic) == "When is my DBMS exam?"


def test_langgraph_agent_and_orchestrator_multi_turn_memory(demo_app):
    o = demo_app.orchestrator
    agent = System2Agent(demo_app.db, o.reasoner, o.engine)
    assert "contextualize" in set(agent.graph.get_graph().nodes)

    tid_a = demo_app.db.create_thread()
    tid_b = demo_app.db.create_thread()

    # Turn 1 on thread A
    a1 = o.handle("Explain deadlock from my OS notes", thread_id=tid_a)
    assert a1.thread_id == tid_a
    assert a1.path == "S2" and "deadlock" in a1.text.lower()

    # Turn 2 follow-up on thread A resolves "its" -> "deadlock" and cites OS notes
    a2 = o.handle("What are its four conditions?", thread_id=tid_a)
    assert a2.thread_id == tid_a
    assert any(s.name == "s1.context" for s in a2.trace)
    assert "circular wait" in a2.text.lower()
    assert any(c.startswith("os_notes") for c in a2.citations)

    # Check messages persisted on thread A; thread B stays isolated
    msgs_a = demo_app.db.thread_messages(tid_a)
    assert [m["role"] for m in msgs_a] == ["user", "assistant", "user", "assistant"]
    assert demo_app.db.thread_messages(tid_b) == []

    # General-knowledge & RAG reasoner receives sliding history
    captured_histories: list[list[dict[str, str]] | None] = []

    class SpyReasoner:
        name = "spy"
        calls = 0

        def contextualize(self, question, history):
            return contextualize_followup(question, history)

        def plan_queries(self, question):
            return [question]

        def answer(self, question, chunks, *, history=None):
            self.calls += 1
            captured_histories.append(history)
            return "Circular wait is one condition [1]." if chunks else "I don't know based on your documents."

        def answer_general(self, question, *, history=None):
            self.calls += 1
            captured_histories.append(history)
            return "General follow-up answer."

    from smriti.app import build_app

    app2 = build_app(Settings(data_dir=demo_app.settings.data_dir, passphrase="demo", llm_backend="extractive"))
    app2.orchestrator.reasoner = SpyReasoner()
    tid_spy = app2.db.create_thread()
    app2.orchestrator.handle("Who is Alan Turing?", thread_id=tid_spy)
    app2.orchestrator.handle("When was he born?", thread_id=tid_spy)
    assert len(captured_histories) >= 2
    assert captured_histories[-1] and captured_histories[-1][0]["content"] == "Who is Alan Turing?"


def test_chat_history_redacts_inline_credentials(tmp_path):
    from smriti.app import build_app
    from smriti.university import SamarthAuthError, SamarthClient

    class FailAuthClient(SamarthClient):
        def fetch_attendance(self, roll_number: str, password: str):
            raise SamarthAuthError("Invalid credentials")

    app = build_app(Settings(data_dir=tmp_path / "data", passphrase="test-vault-pass", llm_backend="extractive"))
    app.orchestrator.samarth_client = FailAuthClient()
    tid = app.db.create_thread()
    app.orchestrator.handle("Check my attendance roll no 23001001065 password SuperSecret99", thread_id=tid)
    msgs = app.db.thread_messages(tid)
    assert msgs and "SuperSecret99" not in msgs[0]["content"]
