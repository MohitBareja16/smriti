"""System 2: the slow, deliberate agent, built as a LangGraph state machine (issue #19).

plan search queries → search (course/semester filters) → if nothing found, broaden and search again →
run the tools System 1 selected → guard retrieved chunks → answer from the sources with citations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TypedDict

from langgraph.graph import END, StateGraph

from smriti.decision.base import DecisionEngine
from smriti.decision.facts_match import fact_score, qualifiers_conflict
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
    for n in _CITE.findall(text):
        i = int(n) - 1
        if 0 <= i < len(chunks) and chunks[i].ref not in refs:
            refs.append(chunks[i].ref)
    return refs


class AgentState(TypedDict, total=False):
    """Everything the System-2 graph passes between nodes for one question."""

    question: str
    intent: str
    widen: bool
    tracer: Tracer
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


class System2Agent:
    """System 2 as a LangGraph state machine:

        plan → act ─(nothing found in scope)→ broaden → act
                  └─(found / out of steps)──→ tools → guard → answer → END

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
        self.graph = self._build()

    def _build(self):
        g = StateGraph(AgentState)
        for name, fn in [("plan", self._plan), ("act", self._act), ("broaden", self._broaden),
                         ("tools", self._tools), ("guard", self._guard), ("answer", self._answer)]:
            g.add_node(name, fn)
        g.set_entry_point("plan")
        g.add_edge("plan", "act")
        g.add_conditional_edges("act", self._decide, {"broaden": "broaden", "continue": "tools"})
        g.add_edge("broaden", "act")
        g.add_edge("tools", "guard")
        g.add_edge("guard", "answer")
        g.add_edge("answer", END)
        return g.compile()

    def run(self, question: str, tracer: Tracer, *, intent: str = "other", widen: bool = False) -> Draft:
        out = self.graph.invoke({"question": question, "intent": intent, "widen": widen, "tracer": tracer})
        chunks, text = out["chunks"], out["text"]
        return Draft(text=text, chunks=chunks, citations=cited_refs(text, chunks), verdicts=out["verdicts"])

    # ---- nodes -------------------------------------------------------------------------------
    def _plan(self, s: AgentState) -> AgentState:
        question, intent, widen = s["question"], s["intent"], s["widen"]
        with s["tracer"].span("s2.plan") as span:
            # System 1 decides whether planning is worth an LLM call: only multi-part questions need it.
            if intent in MULTI_QUERY_INTENTS:
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

    def _act(self, s: AgentState) -> AgentState:
        pool, filters = dict(s["pool"]), s["filters"]
        scope = _scope(filters)
        tool = s["search_tool"] if filters.get("kind") else "search"
        for q in s["queries"]:
            with s["tracer"].span(f"s2.tool.{tool}", query=q, **filters) as span:
                hits = self.db.search(q, k=s["k"], **filters)
                span["detail"] = f"'{q}' [{scope}] → {len(hits)} hits"
            for c in hits:
                pool.setdefault(c.id, c)
        return {"pool": pool}

    def _decide(self, s: AgentState) -> str:
        if s["pool"] or not s["filters"] or s["step"] >= self.max_steps:
            return "continue"
        return "broaden"

    def _broaden(self, s: AgentState) -> AgentState:
        with s["tracer"].span("s2.replan") as span:
            span["detail"] = f"step {s['step']}: no results in [{_scope(s['filters'])}], searching all documents"
        return {"filters": {}, "step": s["step"] + 1}

    def _tools(self, s: AgentState) -> AgentState:
        chunks = sorted(s["pool"].values(), key=lambda c: -c.score)[: s["k"] + 2]
        if "facts_lookup" in s["extra_tools"]:
            with s["tracer"].span("s2.tool.facts_lookup") as span:
                facts = top_facts(s["question"], self.db.all_facts())
                chunks = [Chunk(id=-100 - i, doc_id=f.doc_id, doc_title=f.doc_title, page=f.page,
                                text=f"{f.attribute}: {f.value}", kind="personal")
                          for i, f in enumerate(facts)] + chunks
                span["detail"] = " | ".join(f"{f.attribute}: {f.value}" for f in facts) or "no matching facts"
        if "get_document" in s["extra_tools"]:
            with s["tracer"].span("s2.tool.get_document") as span:
                doc = best_document(s["question"], self.db.list_documents())
                pages = self.db.document_chunks(doc["id"])[:3] if doc else []
                chunks = pages + [c for c in chunks if c.id not in {p.id for p in pages}]
                span["detail"] = f"{doc['title']} ({len(pages)} passages)" if doc else "no matching document"
        if "graph_lookup" in s["extra_tools"]:
            with s["tracer"].span("s2.tool.graph_lookup") as span:
                facts = KnowledgeGraph(self.db).lookup(s["question"])
                graph_chunks = [Chunk(id=-i, doc_id=0, doc_title="knowledge graph", page=0, text=f.text,
                                      label=f"knowledge graph ({', '.join(f.refs[:4])})" if f.refs
                                      else "knowledge graph") for i, f in enumerate(facts, 1)]
                chunks = graph_chunks + chunks
                span["detail"] = f"{len(facts)} fact(s): " + " | ".join(f.text[:80] for f in facts)
        return {"chunks": chunks}

    def _guard(self, s: AgentState) -> AgentState:
        if not self.guard_chunks:
            return {}
        with s["tracer"].span("s1.guard.chunks") as span:
            chunks, verdict = filter_chunks(s["chunks"], self.engine)
            span["detail"] = verdict.detail
        return {"chunks": chunks, "verdicts": [*s["verdicts"], verdict]}

    def _answer(self, s: AgentState) -> AgentState:
        with s["tracer"].span("s2.answer", sources=len(s["chunks"])) as span:
            text = self.reasoner.answer(s["question"], s["chunks"])
            span["detail"] = f"{len(s['chunks'])} sources"
        return {"text": text}

    def plain_rag(self, question: str, tracer: Tracer) -> Draft:
        """Baseline B1: retrieve once, answer once. No planning, no guards."""
        with tracer.span("plain.search") as s:
            chunks = self.db.search(question, k=self.top_k)
            s["detail"] = f"{len(chunks)} hits"
        with tracer.span("plain.answer"):
            text = self.reasoner.answer(question, chunks)
        return Draft(text=text, chunks=chunks, citations=cited_refs(text, chunks))
