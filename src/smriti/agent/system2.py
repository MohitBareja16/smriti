"""System 2: the slow, deliberate agent, built as a LangGraph state machine (issue #19).

plan search queries → search (course/semester filters) → if nothing found, broaden and search again →
run the tools System 1 selected → guard retrieved chunks → answer from the sources with citations.
"""

from __future__ import annotations

import re
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, StateGraph

from smriti.decision.base import DecisionEngine
from smriti.decision.facts_match import fact_score, qualifiers_conflict
from smriti.decision.grounding import Grounder, split_sentences
from smriti.decision.text import norm_set, overlap_f1
from smriti.graph import KnowledgeGraph
from smriti.guardrails import filter_chunks
from smriti.library import detect_semester
from smriti.llm.base import Reasoner
from smriti.observability import Tracer
from smriti.storage import Database
from smriti.types import Chunk, Fact, GuardVerdict

_CITE = re.compile(r"\[(\d+)\]")
MULTI_QUERY_INTENTS = {"compare", "exam_prep", "connect", "other"}

# System 1 chooses the tools from the intent (no LLM tool-calling: cheaper and predictable on small
# local models). "search" scopes: library_search = study material, vault_search = personal documents,
# search = everything. A scope that finds nothing is broadened to all documents.
TOOL_PLANS: dict[str, tuple[str, tuple[str, ...]]] = {
    "fact_lookup": ("vault_search", ("facts_lookup",)),
    "fetch_doc": ("vault_search", ("get_document",)),
    "explain": ("library_search", ()),
    "compare": ("library_search", ()),
    "exam_prep": ("library_search", ()),
    "connect": ("library_search", ("graph_lookup",)),
    "other": ("search", ()),
}
SEARCH_KIND = {"library_search": "library", "vault_search": "personal", "search": None}


@dataclass
class Draft:
    text: str
    chunks: list[Chunk]
    citations: list[str]
    verdicts: list[GuardVerdict] = field(default_factory=list)


def detect_course(question: str, courses: list[str]) -> str | None:
    q = question.lower()
    for course in courses:
        if re.search(rf"\b{re.escape(course.lower())}\b", q):
            return course
    return None


def top_facts(question: str, facts: list[Fact], n: int = 3) -> list[Fact]:
    """Facts most related to the question (excluding conflicting numbers), as evidence for System 2."""
    q = norm_set(question, drop_generic=True)
    scored = [(fact_score(q, f.attribute), f) for f in facts if not qualifiers_conflict(question, f.attribute)]
    return [f for score, f in sorted(scored, key=lambda x: -x[0]) if score > 0][:n]


def best_document(question: str, documents) -> dict | None:
    q = norm_set(question, drop_generic=True)
    scored = sorted(((overlap_f1(q, norm_set(f"{d['title']} {d['doc_type']}".replace("_", " "))), d)
                     for d in documents), key=lambda x: -x[0])
    return scored[0][1] if scored and scored[0][0] > 0 else None


def _scope(filters: dict) -> str:
    return ", ".join(f"{name}={value}" for name, value in filters.items()) or "all documents"


def cited_refs(text: str, chunks: list[Chunk]) -> list[str]:
    refs: list[str] = []
    if not chunks or not text.strip():
        return refs
    grounder = Grounder(rule="lexical")
    for sentence in split_sentences(text):
        claim = _CITE.sub("", sentence).strip()
        if len(claim) <= 3:
            continue
        cited = [int(n) - 1 for n in _CITE.findall(sentence)]
        candidates = [i for i in cited if 0 <= i < len(chunks)] if cited else range(len(chunks))
        for i in candidates:
            if grounder.check([claim], [chunks[i].text])[0].label == "yes":
                if chunks[i].ref not in refs:
                    refs.append(chunks[i].ref)
                # Keep a grounded inline citation; for an uncited answer, use the first
                # source verified against the sentence instead of the top ranked chunk.
                if cited:
                    continue
                break
    return refs


class AgentState(TypedDict, total=False):
    """Everything the System-2 graph passes between nodes for one question."""

    question: str
    raw_question: str
    intent: str
    widen: bool
    history: list[dict[str, str]]
    already_contextualized: bool
    search_tool: str
    extra_tools: tuple[str, ...]
    queries: list[str]
    filters: dict
    step: int
    k: int
    pool: dict[int, Chunk]
    chunks: list[Chunk]
    verdicts: list[GuardVerdict]
    text: str


def _tracer(config: RunnableConfig) -> Tracer:
    return (config.get("configurable") or {})["tracer"]


def _on_token(config: RunnableConfig) -> Callable[[str], None] | None:
    return (config.get("configurable") or {}).get("on_token")


def _cancel_event(config: RunnableConfig) -> threading.Event | None:
    return (config.get("configurable") or {}).get("cancel_event")


def _needs_llm_plan(question: str, intent: str) -> bool:
    """Skip slow LLM query planning for short single-concept questions on CPU."""
    if intent in {"compare", "exam_prep", "connect"}:
        return True
    if intent != "other":
        return False
    low = question.lower()
    return len(question.split()) > 9 or any(k in low for k in (" vs ", " versus ", " compare ", " difference ", " both "))


def _call_reasoner(
    fn,
    *args,
    history=None,
    on_token=None,
    cancel_event: threading.Event | None = None,
) -> str:
    """Invoke reasoner answer/answer_general passing optional kwargs only when supported."""
    attempts = [
        {"history": history, "on_token": on_token, "cancel_event": cancel_event},
        {"history": history, "on_token": on_token},
        {"history": history},
        {},
    ]
    for kw in attempts:
        try:
            return fn(*args, **kw)
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc) and "keyword" not in str(exc):
                raise
    return fn(*args)


class System2Agent:
    """System 2 as a LangGraph state machine:

        contextualize → plan → act ─(nothing found in scope)→ broaden → act
                                 └─(found / out of steps)──→ tools → guard → answer → END

    `contextualize` resolves follow-up references against the thread's sliding history window;
    `plan` (LLM, multi-part questions only) writes search queries; `act` searches with course and
    semester filters; `broaden` drops the filters; `tools` runs the extra tools the System-1 intent
    calls for (e.g. graph_lookup for 'connect'); `guard` strips injected text; `answer` (LLM)
    writes a cited answer. Every node is a traced span.
    """

    def __init__(self, db: Database, reasoner: Reasoner, engine: DecisionEngine, *, top_k: int = 5,
                 max_steps: int = 2, guard_chunks: bool = True, use_tools: bool = True):
        self.db, self.reasoner, self.engine = db, reasoner, engine
        self.top_k, self.max_steps, self.guard_chunks = top_k, max_steps, guard_chunks
        self.use_tools = use_tools  # False = only search (+ graph for 'connect'), as before #19
        try:
            serde = JsonPlusSerializer(
                allowed_msgpack_modules=[("smriti.types", "Chunk"), ("smriti.types", "GuardVerdict")]
            )
        except TypeError:
            serde = JsonPlusSerializer()
        self.checkpointer = MemorySaver(serde=serde)
        self.graph = self._build()

    def _build(self):
        g = StateGraph(AgentState)
        for name, fn in [
            ("contextualize", self._contextualize),
            ("plan", self._plan),
            ("act", self._act),
            ("broaden", self._broaden),
            ("tools", self._tools),
            ("guard", self._guard),
            ("answer", self._answer),
        ]:
            g.add_node(name, fn)
        g.set_entry_point("contextualize")
        g.add_edge("contextualize", "plan")
        g.add_edge("plan", "act")
        g.add_conditional_edges("act", self._decide, {"broaden": "broaden", "continue": "tools"})
        g.add_edge("broaden", "act")
        g.add_edge("tools", "guard")
        g.add_edge("guard", "answer")
        g.add_edge("answer", END)
        return g.compile(checkpointer=self.checkpointer)

    def run(
        self,
        question: str,
        tracer: Tracer,
        *,
        intent: str = "other",
        widen: bool = False,
        history: list[dict[str, str]] | None = None,
        thread_id: str | None = None,
        raw_question: str | None = None,
        already_contextualized: bool = False,
        on_token: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Draft:
        state_in: AgentState = {
            "question": question,
            "raw_question": raw_question or question,
            "intent": intent,
            "widen": widen,
            "history": list(history or ()),
            "already_contextualized": already_contextualized,
            "queries": [],
            "filters": {},
            "step": 0,
            "pool": {},
            "chunks": [],
            "verdicts": [],
            "text": "",
        }
        run_thread = thread_id or f"_eph_{uuid.uuid4().hex}"
        cfg = {
            "configurable": {
                "thread_id": run_thread,
                "tracer": tracer,
                "on_token": on_token,
                "cancel_event": cancel_event,
            }
        }
        try:
            out = self.graph.invoke(state_in, config=cfg)
        finally:
            if thread_id is None and hasattr(self.checkpointer, "delete_thread"):
                self.checkpointer.delete_thread(run_thread)
        chunks, text = out["chunks"], out["text"]
        return Draft(text=text, chunks=chunks, citations=cited_refs(text, chunks), verdicts=out["verdicts"])

    # ---- nodes -------------------------------------------------------------------------------
    def _contextualize(self, s: AgentState, config: RunnableConfig) -> AgentState:
        history = s.get("history") or []
        question = s["question"]
        if not history or s.get("already_contextualized"):
            return {}
        rewritten = (
            self.reasoner.contextualize(question, history)
            if hasattr(self.reasoner, "contextualize")
            else question
        )
        if rewritten != question:
            with _tracer(config).span("s2.contextualize") as span:
                span["detail"] = f"{question!r} → {rewritten!r}"
        return {"question": rewritten}
    def _plan(self, s: AgentState, config: RunnableConfig) -> AgentState:
        question, intent, widen = s["question"], s["intent"], s["widen"]
        with _tracer(config).span("s2.plan") as span:
            # System 1 decides whether planning is worth an LLM call: only multi-part questions need it.
            if _needs_llm_plan(question, intent):
                queries = self.reasoner.plan_queries(question)
                if question not in queries:
                    queries.append(question)
            else:
                queries = [question]
            span["detail"] = " | ".join(queries)
        search_tool, extra_tools = TOOL_PLANS.get(intent, TOOL_PLANS["other"]) if self.use_tools else ("search", ())
        # personal documents have no course, so the vault search scopes by semester only
        course = None if search_tool == "vault_search" else detect_course(question, self.db.courses())
        filters = {} if widen else {"course": course, "semester": detect_semester(question),
                                    "kind": SEARCH_KIND[search_tool]}
        if intent == "connect" and not self.use_tools:
            extra_tools = ("graph_lookup",)
        return {"queries": queries, "filters": {k: v for k, v in filters.items() if v is not None},
                "search_tool": search_tool if filters.get("kind") else "search", "extra_tools": extra_tools,
                "step": 1, "k": self.top_k * (2 if widen else 1), "pool": {}, "verdicts": []}

    def _act(self, s: AgentState, config: RunnableConfig) -> AgentState:
        pool, filters = dict(s["pool"]), s["filters"]
        scope = _scope(filters)
        tool = s["search_tool"] if filters.get("kind") else "search"
        tracer = _tracer(config)
        for q in s["queries"]:
            with tracer.span(f"s2.tool.{tool}", query=q, **filters) as span:
                hits = self.db.search(q, k=s["k"], **filters)
                span["detail"] = f"'{q}' [{scope}] → {len(hits)} hits"
            for c in hits:
                pool.setdefault(c.id, c)

        # Whole-document fallback / named-document boost (also surfaces personal PDFs when explicitly named)
        q_low = s["question"].lower()
        req_sem = s["filters"].get("semester")
        req_course = s["filters"].get("course")
        named_docs = [
            d
            for d in self.db.find_matching_documents(s["question"], kind=None, limit=2)
            if (req_sem is None or d["semester"] == req_sem)
            and (req_course is None or (d["course"] or "").lower() == req_course.lower())
        ]
        if not named_docs and any(
            k in q_low for k in ("just uploaded", "uploaded pdf", "recently indexed", "latest pdf")
        ):
            all_docs = self.db.list_documents()
            if all_docs:
                named_docs = [all_docs[-1]]
        wants_summary = any(k in q_low for k in ("summar", "overview", "topics", "important questions", "key points", "inside", "what is in"))
        if named_docs and (wants_summary or not pool):
            for d in named_docs:
                for idx, c in enumerate(self.db.document_chunks(int(d["id"]))[:10]):
                    if c.id not in pool:
                        pool[c.id] = Chunk(
                            id=c.id, doc_id=c.doc_id, doc_title=c.doc_title, page=c.page, text=c.text,
                            course=c.course, kind=c.kind, score=100.0 - idx * 0.01, topic=c.topic,
                        )
        return {"pool": pool}

    def _decide(self, s: AgentState) -> str:
        if s["pool"] or not s["filters"] or s["step"] >= self.max_steps:
            return "continue"
        return "broaden"

    def _broaden(self, s: AgentState, config: RunnableConfig) -> AgentState:
        with _tracer(config).span("s2.replan") as span:
            span["detail"] = f"step {s['step']}: no results in [{_scope(s['filters'])}], searching all documents"
        return {"filters": {}, "step": s["step"] + 1}

    def _tools(self, s: AgentState, config: RunnableConfig) -> AgentState:
        chunks = sorted(s["pool"].values(), key=lambda c: -c.score)[: s["k"] + 2]
        tracer = _tracer(config)
        if "facts_lookup" in s["extra_tools"]:
            with tracer.span("s2.tool.facts_lookup") as span:
                facts = top_facts(s["question"], self.db.all_facts())
                chunks = [Chunk(id=-100 - i, doc_id=f.doc_id, doc_title=f.doc_title, page=f.page,
                                text=f"{f.attribute}: {f.value}", kind="personal")
                          for i, f in enumerate(facts)] + chunks
                span["detail"] = " | ".join(f"{f.attribute}: {f.value}" for f in facts) or "no matching facts"
        if "get_document" in s["extra_tools"]:
            with tracer.span("s2.tool.get_document") as span:
                doc = best_document(s["question"], self.db.list_documents())
                pages = self.db.document_chunks(doc["id"])[:3] if doc else []
                chunks = pages + [c for c in chunks if c.id not in {p.id for p in pages}]
                span["detail"] = f"{doc['title']} ({len(pages)} passages)" if doc else "no matching document"
        if "graph_lookup" in s["extra_tools"]:
            with tracer.span("s2.tool.graph_lookup") as span:
                facts = KnowledgeGraph(self.db).lookup(s["question"])
                graph_chunks = [Chunk(id=-i, doc_id=0, doc_title="knowledge graph", page=0, text=f.text,
                                      label=f"knowledge graph ({', '.join(f.refs[:4])})" if f.refs
                                      else "knowledge graph") for i, f in enumerate(facts, 1)]
                chunks = graph_chunks + chunks
                span["detail"] = f"{len(facts)} fact(s): " + " | ".join(f.text[:80] for f in facts)
        return {"chunks": chunks}

    def _guard(self, s: AgentState, config: RunnableConfig) -> AgentState:
        if not self.guard_chunks:
            return {}
        with _tracer(config).span("s1.guard.chunks") as span:
            chunks, verdict = filter_chunks(s["chunks"], self.engine)
            span["detail"] = verdict.detail
        return {"chunks": chunks, "verdicts": [*s["verdicts"], verdict]}

    def _answer(self, s: AgentState, config: RunnableConfig) -> AgentState:
        history = s.get("history") or None
        token_cb = _on_token(config)
        cancel_ev = _cancel_event(config)
        with _tracer(config).span("s2.answer", sources=len(s["chunks"])) as span:
            if s["chunks"]:
                text = _call_reasoner(
                    self.reasoner.answer,
                    s["question"],
                    s["chunks"],
                    history=history,
                    on_token=token_cb,
                    cancel_event=cancel_ev,
                )
                span["detail"] = f"{len(s['chunks'])} sources"
            elif hasattr(self.reasoner, "answer_general"):
                text = _call_reasoner(
                    self.reasoner.answer_general,
                    s["raw_question"] or s["question"],
                    history=history,
                    on_token=token_cb,
                    cancel_event=cancel_ev,
                )
                span["detail"] = "0 sources (general knowledge)"
            else:
                text = self.reasoner.answer(s["question"], s["chunks"])
                span["detail"] = "0 sources"
        return {"text": text}

    def plain_rag(self, question: str, tracer: Tracer) -> Draft:
        """Baseline B1: retrieve once, answer once. No planning, no guards."""
        with tracer.span("plain.search") as s:
            chunks = self.db.search(question, k=self.top_k)
            s["detail"] = f"{len(chunks)} hits"
        with tracer.span("plain.answer"):
            text = self.reasoner.answer(question, chunks)
        return Draft(text=text, chunks=chunks, citations=cited_refs(text, chunks))
