"""System 2: the slow, deliberate agent.

Loop: plan search queries → search (with course filters) → guard retrieved chunks → if nothing useful,
broaden and search again → answer from the sources with citations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from smriti.decision.base import DecisionEngine
from smriti.guardrails import filter_chunks
from smriti.library import detect_semester
from smriti.llm.base import Reasoner
from smriti.observability import Tracer
from smriti.storage import Database
from smriti.types import Chunk, GuardVerdict

_CITE = re.compile(r"\[(\d+)\]")
MULTI_QUERY_INTENTS = {"compare", "exam_prep", "other"}


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


def cited_refs(text: str, chunks: list[Chunk]) -> list[str]:
    refs: list[str] = []
    for n in _CITE.findall(text):
        i = int(n) - 1
        if 0 <= i < len(chunks) and chunks[i].ref not in refs:
            refs.append(chunks[i].ref)
    return refs


class System2Agent:
    def __init__(self, db: Database, reasoner: Reasoner, engine: DecisionEngine, *, top_k: int = 5,
                 max_steps: int = 2, guard_chunks: bool = True):
        self.db, self.reasoner, self.engine = db, reasoner, engine
        self.top_k, self.max_steps, self.guard_chunks = top_k, max_steps, guard_chunks

    def run(self, question: str, tracer: Tracer, *, intent: str = "other", widen: bool = False) -> Draft:
        with tracer.span("s2.plan") as s:
            # System 1 decides whether planning is worth an LLM call: only multi-part questions need it.
            if intent in MULTI_QUERY_INTENTS:
                queries = self.reasoner.plan_queries(question)
                if question not in queries:
                    queries.append(question)
            else:
                queries = [question]
            s["detail"] = " | ".join(queries)

        filters = {} if widen else {"course": detect_course(question, self.db.courses()),
                                    "semester": detect_semester(question)}
        filters = {k: v for k, v in filters.items() if v is not None}
        k = self.top_k * (2 if widen else 1)
        pool: dict[int, Chunk] = {}
        verdicts: list[GuardVerdict] = []
        for step in range(1, self.max_steps + 1):
            scope = ", ".join(f"{name}={value}" for name, value in filters.items()) or "all documents"
            for q in queries:
                with tracer.span("s2.tool.search", query=q, **filters) as s:
                    hits = self.db.search(q, k=k, **filters)
                    s["detail"] = f"'{q}' [{scope}] → {len(hits)} hits"
                for c in hits:
                    pool.setdefault(c.id, c)
            if pool or not filters:
                break
            filters = {}  # nothing found inside the scope: broaden the search (agent's second step)
            with tracer.span("s2.replan") as s:
                s["detail"] = f"step {step}: no results in [{scope}], searching all documents"

        chunks = sorted(pool.values(), key=lambda c: -c.score)[: k + 2]
        if self.guard_chunks:
            with tracer.span("s1.guard.chunks") as s:
                chunks, verdict = filter_chunks(chunks, self.engine)
                verdicts.append(verdict)
                s["detail"] = verdict.detail

        with tracer.span("s2.answer", sources=len(chunks)) as s:
            text = self.reasoner.answer(question, chunks)
            s["detail"] = f"{len(chunks)} sources"
        return Draft(text=text, chunks=chunks, citations=cited_refs(text, chunks), verdicts=verdicts)

    def plain_rag(self, question: str, tracer: Tracer) -> Draft:
        """Baseline B1: retrieve once, answer once. No planning, no guards."""
        with tracer.span("plain.search") as s:
            chunks = self.db.search(question, k=self.top_k)
            s["detail"] = f"{len(chunks)} hits"
        with tracer.span("plain.answer"):
            text = self.reasoner.answer(question, chunks)
        return Draft(text=text, chunks=chunks, citations=cited_refs(text, chunks))
