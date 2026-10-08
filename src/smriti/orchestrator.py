"""The System-1 → System-2 escalation policy (the core of the project).

    question → G1 input guard → S1 router (+confidence)
        ├─ fact_lookup and confident → S1 direct answer from the facts table (no LLM)
        ├─ fetch_doc   and confident → S1 fetches the document from the vault
        └─ otherwise → ESCALATE to the S2 agent → G2 grounding: drop unsupported sentences
           (retry wider once if nothing is supported) → G3 PII leak → answer
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

from smriti.agent import System2Agent
from smriti.agent.system2 import cited_refs
from smriti.config import Settings
from smriti.decision import DecisionEngine, match_fact
from smriti.decision.grounding import Grounder
from smriti.decision.text import norm_set, overlap_f1
from smriti.guardrails import IDK, GroundingResult, check_input, check_pii, ground_answer
from smriti.llm.base import Reasoner
from smriti.observability import Tracer
from smriti.storage import Database
from smriti.types import Answer
from smriti.vault import Vault, VaultLockedError

Mode = Literal["ours", "agent", "plain"]
BLOCKED_TEXT = "I can't help with that: the request looks like a prompt-injection or data-extraction attempt."


class Orchestrator:
    def __init__(self, settings: Settings, db: Database, vault: Vault, engine: DecisionEngine,
                 reasoner: Reasoner):
        self.settings, self.db, self.vault, self.engine, self.reasoner = settings, db, vault, engine, reasoner
        thr = settings.grounding_threshold
        self.grounder = Grounder(rule=settings.grounding, thresholds={settings.grounding: thr} if thr else {})

    def handle(self, question: str, *, mode: Mode = "ours", guardrails: bool = True,
               tau: float | None = None) -> Answer:
        """mode='ours' is S1+S2; 'agent' always uses S2; 'plain' is the plain-RAG baseline.

        `tau` overrides the System-1 confidence threshold (settings.tau_fast) for experiments.
        """
        tracer = Tracer()
        tau = self.settings.tau_fast if tau is None else tau
        start, calls_before = time.perf_counter(), self.reasoner.calls
        tokens_before = getattr(self.reasoner, "tokens", 0)
        answer = self._handle(question, mode, guardrails, tracer, tau)
        answer.trace = tracer.steps
        answer.latency_ms = (time.perf_counter() - start) * 1000
        answer.llm_calls = self.reasoner.calls - calls_before
        answer.llm_tokens = getattr(self.reasoner, "tokens", 0) - tokens_before
        self.db.audit("ask", f"path={answer.path} intent={answer.intent} q={question[:80]!r}")
        return answer

    def _ground(self, text: str, chunks) -> GroundingResult:
        return ground_answer(text, chunks, self.grounder, policy=self.settings.grounding_policy,
                             threshold=self.settings.tau_grounding)

    def system1_candidate(self, question: str) -> Answer | None:
        """What System 1 would answer on its own, with its confidence, ignoring the threshold.

        Used by research experiments (e.g. the tau sweep): System 1 answers alone exactly when
        `candidate.confidence >= tau`, so one probe per question covers every threshold.
        """
        tracer = Tracer()
        route = self.engine.route(question)
        return self._fast_path(question, route.label, route.probability, tracer, tau=0.0)

    def _handle(self, question: str, mode: Mode, guardrails: bool, tracer: Tracer, tau: float) -> Answer:
        agent = System2Agent(self.db, self.reasoner, self.engine, top_k=self.settings.top_k,
                             max_steps=self.settings.max_agent_steps, guard_chunks=guardrails)
        if mode == "plain":
            draft = agent.plain_rag(question, tracer)
            return Answer(text=draft.text, citations=draft.citations, path="PLAIN")

        verdicts = []
        if guardrails:
            with tracer.span("s1.guard.input") as s:
                v = check_input(question, self.engine)
                verdicts.append(v)
                s["detail"] = f"{v.detail} (p_injection={v.score:.2f})"
            if not v.passed:
                return Answer(text=BLOCKED_TEXT, path="BLOCKED", guard_verdicts=verdicts)

        with tracer.span("s1.router") as s:
            route = self.engine.route(question)
            s["detail"] = f"{route.label} (p={route.probability:.2f})"

        if mode == "ours" and route.probability >= tau:
            fast = self._fast_path(question, route.label, route.probability, tracer, tau)
            if fast is not None:
                fast.guard_verdicts = verdicts + fast.guard_verdicts
                return fast

        with tracer.span("escalate") as s:
            s["detail"] = f"to System 2 (intent={route.label}, p={route.probability:.2f}, " \
                          f"tau={tau})"
        draft = agent.run(question, tracer, intent=route.label)
        verdicts += draft.verdicts
        text, citations = draft.text, draft.citations

        if guardrails:
            with tracer.span("s1.guard.grounding") as s:
                g = self._ground(text, draft.chunks)
                s["detail"] = f"{g.verdict.detail} (score={g.verdict.score:.2f})"
            if not g.verdict.passed:
                with tracer.span("s2.retry") as s:
                    s["detail"] = "nothing grounded: searching wider and answering again"
                draft = agent.run(question, tracer, intent=route.label, widen=True)
                with tracer.span("s1.guard.grounding") as s:
                    g = self._ground(draft.text, draft.chunks)
                    s["detail"] = f"{g.verdict.detail} (score={g.verdict.score:.2f})"
            if g.verdict.passed:
                text, citations = g.text, cited_refs(g.text, draft.chunks)
            else:
                text, citations = IDK, []
            verdicts.append(g.verdict)
            with tracer.span("s1.guard.pii") as s:
                text, p = check_pii(text, question)
                verdicts.append(p)
                s["detail"] = p.detail

        return Answer(text=text, citations=citations, path="S2", intent=route.label,
                      confidence=route.probability, guard_verdicts=verdicts)

    # ---- System 1 fast path ----------------------------------------------------------------
    def _fast_path(self, question: str, intent: str, p_route: float, tracer: Tracer,
                   tau: float) -> Answer | None:
        if intent == "fact_lookup":
            with tracer.span("s1.facts_lookup") as s:
                m = match_fact(question, self.db.all_facts())
                p = p_route * m.score if m else 0.0
                s["detail"] = (f"'{m.fact.attribute}' match={m.score:.2f} → p={p:.2f}" if m else "no match")
            if m and p >= tau:
                f = m.fact
                return Answer(text=f"{f.attribute}: {f.value}", citations=[f"{f.doc_title} p.{f.page}"],
                              path="S1", intent=intent, confidence=p)
        elif intent == "fetch_doc":
            with tracer.span("s1.fetch_doc") as s:
                answer = self._fetch(question, p_route, tau)
                s["detail"] = answer.text if answer else "no confident document match"
            return answer
        return None

    def _fetch(self, question: str, p_route: float, tau: float) -> Answer | None:
        q = norm_set(question, drop_generic=True)
        scored = sorted(((overlap_f1(q, norm_set(f"{d['title']} {d['doc_type']}".replace("_", " "))), d)
                         for d in self.db.list_documents()), key=lambda x: -x[0])
        if not scored or scored[0][0] == 0:
            return None
        score, doc = scored[0]
        if len(scored) > 1 and scored[1][0] >= score:
            score *= 0.5
        p = p_route * min(1.0, score * 1.5)
        if p < tau:
            return None
        cite = [f"{doc['title']} (document)"]
        if not doc["vault_file"]:
            return Answer(text=f"Found '{doc['title']}': {doc['path']}", citations=cite, path="S1",
                          intent="fetch_doc", confidence=p, attachment=doc["path"])
        try:
            data = self.vault.get(doc["vault_file"])
        except VaultLockedError:
            return Answer(text=f"Found '{doc['title']}', but the vault is locked. Set SMRITI_PASSPHRASE.",
                          citations=cite, path="S1", intent="fetch_doc", confidence=p)
        out_dir = self.settings.data_dir / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{doc['title']}{Path(doc['path']).suffix}"
        out.write_bytes(data)
        self.db.audit("fetch", f"decrypted {doc['title']} to {out}")
        return Answer(text=f"Here is '{doc['title']}' (decrypted copy): {out}", citations=cite, path="S1",
                      intent="fetch_doc", confidence=p, attachment=str(out))
