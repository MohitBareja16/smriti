"""The System-1 → System-2 escalation policy (the core of the project).

    question → G1 input guard → S1 router (+confidence)
        ├─ fact_lookup and confident → S1 direct answer from the facts table (no LLM)
        ├─ fetch_doc   and confident → S1 fetches the document from the vault
        └─ otherwise → ESCALATE to the S2 agent → G2 grounding: drop unsupported sentences
           (retry wider once if nothing is supported) → G3 PII leak → answer
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from smriti.agent import System2Agent
from smriti.agent.system2 import _call_reasoner, cited_refs
from smriti.config import Settings
from smriti.decision import DecisionEngine, match_fact
from smriti.decision.grounding import Grounder
from smriti.decision.text import norm_set, overlap_f1
from smriti.guardrails import IDK, GroundingResult, check_input, check_pii, ground_answer
from smriti.guardrails.pii import redact, redact_credentials
from smriti.llm.base import Reasoner
from smriti.llm.extractive import contextualize_followup
from smriti.observability import Tracer
from smriti.storage import Database, content_tokens
from smriti.types import Answer
from smriti.university import (
    SamarthClient,
    SamarthError,
    analyze_subject_pyqs,
    attendance_to_ui_props,
    format_attendance_markdown,
    format_pyq_html,
    format_pyq_markdown,
    format_syllabus_html,
    format_syllabus_markdown,
    format_timetable_markdown,
    load_pyq_catalog,
    load_samarth_credentials,
    load_syllabus_catalog,
    pyq_to_ui_props,
    search_pyqs,
    search_syllabus,
    syllabus_to_ui_props,
    sync_samarth_attendance,
    sync_samarth_timetable,
    timetable_to_ui_props,
)
from smriti.vault import Vault, VaultLockedError

Mode = Literal["ours", "agent", "plain"]
BLOCKED_TEXT = "I can't help with that: the request looks like a prompt-injection or data-extraction attempt."
_COUNT_DOCUMENTS = re.compile(
    r"\b(?:how many|count|number of)\s+(?:documents?|docs?|files?)\b|"
    r"\b(?:document|doc|file)\s+count\b", re.IGNORECASE)
_WHOLE_LIBRARY_COUNT_TERMS = {
    "document", "documents", "doc", "docs", "file", "files", "there", "all", "total", "overall",
    "indexed", "stored", "library", "vault", "smriti", "currently", "added", "have", "we", "i",
    "many", "number", "count",
}
_GREETING_PATTERN = re.compile(
    r"^\s*(?:hey|hi|hello|namaste|hlo|heyy+|hii+|good\s+(?:morning|afternoon|evening)|who\s+are\s+you|what\s+can\s+you\s+do|help)\b[!.? ]*$",
    re.IGNORECASE,
)
_ROLL_CRED = re.compile(
    r"(?:\b(?:roll\s*(?:no|number)?|enrolment(?:\s*number)?|enrollment(?:\s*number)?|username|user)\b\s*(?:is|:|=)?\s*)([A-Za-z0-9_-]{4,24})",
    re.IGNORECASE,
)
_PASS_CRED = re.compile(
    r'(?:\b(?:password|passwd|pwd|pass)\b\s*(?:is|:|=)?\s*)(?:"([^"]+)"|\'([^\']+)\'|([^\s,;]+))',
    re.IGNORECASE,
)
_LIVE_TIMETABLE = re.compile(
    r"\b(?:samarth|esamarth|e-samarth)\b[^.?]*\b(?:timetable|time\s*table|calendar|schedule)\b|"
    r"\b(?:timetable|time\s*table|schedule)\b[^.?]*\b(?:samarth|esamarth|e-samarth|calendar)\b|"
    r"\b(?:sync|refresh|fetch)\b[^.?]*\b(?:timetable|time\s*table|calendar)\b|"
    r"^\s*(?:my\s+)?(?:calendar|class\s+calendar|weekly\s+timetable)\s*\??$",
    re.IGNORECASE,
)
_LIVE_ATTENDANCE = re.compile(
    r"\b(?:samarth|esamarth|e-samarth|a10dance)\b|"
    r"\b(?:fetch|sync|refresh|update|check|get|show)\b[^.?]*\battendance\b|"
    r"^\s*(?:my\s+)?attendance(?:\s+(?:report|status|summary))?\s*\??$",
    re.IGNORECASE,
)
_SUBJECT_SPECIFIC = re.compile(
    r"\battendance\s+(?:in|of|for)\s+(?!all\b|my\b|semester\b|samarth\b)[a-z0-9]{2,}",
    re.IGNORECASE,
)
_PYQ_MENTION = re.compile(
    r"\b(?:pyqs?|pqps?|dcrustedp|previous\s+year\s+(?:question\s+)?papers?|"
    r"past\s+papers?|question\s+papers?)\b",
    re.IGNORECASE,
)
_UNIT_HINT_SRC = (
    r"(?:unit|chapter)\s*[-:]?\s*(?:iv|iii|ii|i|[1-4])"
    r"|(?:1st|2nd|3rd|4th|first|second|third|fourth)\s+(?:unit|chapter)"
)
_PYQ_CONTENT_EXCLUSION = re.compile(
    rf"\b(?:topics?|repeated(?:ly)?|come\s+up|most\s+(?:frequently\s+)?asked|frequently|important|"
    rf"revise|study|prepare|asked\s+(?:about|from|in)|questions?\s+asked|what\s+was\s+asked|"
    rf"analy[sz]e|analysis|{_UNIT_HINT_SRC}|order\s+of|summari[sz]e|"
    rf"explain|solve|solutions?|answers?|syllabus|weightage|compare|pattern|trend)\b",
    re.IGNORECASE,
)
_PYQ_ANALYSIS_HINT = re.compile(
    rf"\b(?:analy[sz]e|analysis|{_UNIT_HINT_SRC}|most\s+(?:frequently\s+)?asked|"
    rf"frequently|repeated(?:ly)?|important\s+questions?|key\s+topics?|questions?\s+asked|"
    rf"asked\s+(?:from|in)|what\s+was\s+asked|order\s+of|summari[sz]e|weightage|pattern|trend)\b",
    re.IGNORECASE,
)
_COURSE_OR_SESSION_HINT = re.compile(
    r"\b[A-Za-z]{2,5}\d{2,4}[A-Za-z]?\b|\b(?:jan|feb|mar|apr|may|jun|june|jul|aug|sep|oct|nov|dec)[a-z]*[\s_-]*20\d{2}\b",
    re.IGNORECASE,
)


def _wants_pyq_analysis(question: str, pyq_dir: Path) -> bool:
    if not _PYQ_ANALYSIS_HINT.search(question):
        return False
    if not (_PYQ_MENTION.search(question) or _COURSE_OR_SESSION_HINT.search(question)):
        return False
    return load_pyq_catalog(pyq_dir) is not None


def _wants_pyq_lookup(question: str, pyq_dir: Path) -> bool:
    if not _PYQ_MENTION.search(question) or _PYQ_CONTENT_EXCLUSION.search(question):
        return False
    if load_pyq_catalog(pyq_dir) is not None:
        return True
    return bool(re.search(r"\b(?:pyqs?|pqps?|dcrustedp)\b", question, re.IGNORECASE))


_SYLLABUS_MENTION = re.compile(r"\b(?:syllabus|syllabi)\b", re.IGNORECASE)


def _wants_syllabus_lookup(question: str, syllabus_dir: Path) -> bool:
    if not _SYLLABUS_MENTION.search(question) or _PYQ_MENTION.search(question):
        return False
    return load_syllabus_catalog(syllabus_dir) is not None or bool(
        re.search(r"\b(?:dcrust|branch|year|sem|semester|b\.?\s*tech|m\.?\s*tech|bca|mca)\b", question, re.IGNORECASE)
    )


def _is_whole_library_count(question: str) -> bool:
    return bool(_COUNT_DOCUMENTS.search(question)) and set(content_tokens(question)) <= _WHOLE_LIBRARY_COUNT_TERMS


def _is_greeting(question: str) -> bool:
    return bool(_GREETING_PATTERN.match(question.strip()))


def _extract_samarth_credentials(question: str) -> tuple[str, str] | None:
    roll_m = _ROLL_CRED.search(question)
    pass_m = _PASS_CRED.search(question)
    if roll_m and pass_m:
        pwd = next((g for g in pass_m.groups() if g), "")
        if roll_m.group(1) and pwd:
            return roll_m.group(1).strip(), pwd.strip()
    return None


def _wants_live_timetable(question: str, has_inline_creds: bool) -> bool:
    mentions_tt = bool(re.search(r"\b(?:timetable|time\s*table|calendar)\b", question, re.IGNORECASE))
    mentions_att = bool(re.search(r"\battendance\b", question, re.IGNORECASE))
    if has_inline_creds and mentions_tt and not mentions_att:
        return True
    return bool(_LIVE_TIMETABLE.search(question))


def _wants_live_attendance(question: str, has_inline_creds: bool) -> bool:
    if has_inline_creds:
        return True
    if _SUBJECT_SPECIFIC.search(question):
        return False
    return bool(_LIVE_ATTENDANCE.search(question))


class Orchestrator:
    def __init__(self, settings: Settings, db: Database, vault: Vault, engine: DecisionEngine,
                 reasoner: Reasoner, samarth_client: SamarthClient | None = None):
        self.settings, self.db, self.vault, self.engine, self.reasoner = settings, db, vault, engine, reasoner
        self.samarth_client = samarth_client or SamarthClient()
        thr = settings.grounding_threshold
        self.grounder = Grounder(rule=settings.grounding, thresholds={settings.grounding: thr} if thr else {})
        self._agents: dict[tuple, System2Agent] = {}

    def handle(
        self,
        question: str,
        *,
        mode: Mode = "ours",
        guardrails: bool = True,
        tau: float | None = None,
        thread_id: str | None = None,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Answer:
        """mode='ours' is S1+S2; 'agent' always uses S2; 'plain' is the plain-RAG baseline.

        `tau` overrides the System-1 confidence threshold (settings.tau_fast) for experiments.
        When `thread_id` is provided, loads sliding-window history from `self.db` and persists the turn.
        """
        tracer = Tracer(on_event=on_event)
        tau = self.settings.tau_fast if tau is None else tau
        start, calls_before = time.perf_counter(), self.reasoner.calls
        tokens_before = getattr(self.reasoner, "tokens", 0)
        history: list[dict[str, str]] = []
        if thread_id:
            history = self.db.recent_history(
                thread_id,
                max_turns=self.settings.context_turns,
                max_chars=self.settings.context_max_chars,
            )
        with tracer.request(mode=mode, guardrails=guardrails, tau=tau) as root:
            answer = self._handle(
                question,
                mode,
                guardrails,
                tracer,
                tau,
                history=history,
                thread_id=thread_id,
                on_event=on_event,
                cancel_event=cancel_event,
            )
            root.update(path=answer.path, intent=answer.intent, confidence=round(answer.confidence, 4))
        answer.trace = tracer.steps
        answer.trace_id = tracer.trace_id
        answer.latency_ms = (time.perf_counter() - start) * 1000
        answer.llm_calls = self.reasoner.calls - calls_before
        answer.llm_tokens = getattr(self.reasoner, "tokens", 0) - tokens_before
        self._store_trace(question, answer)
        safe_q = redact_credentials(redact(question))
        if thread_id:
            answer.thread_id = thread_id
            self.db.add_chat_message(thread_id, "user", safe_q)
            self.db.add_chat_message(
                thread_id,
                "assistant",
                answer.text,
                meta={
                    "path": answer.path,
                    "intent": answer.intent,
                    "confidence": round(answer.confidence, 4),
                    "llm_calls": answer.llm_calls,
                    "latency_ms": round(answer.latency_ms, 1),
                    "trace_id": answer.trace_id,
                    "citations": answer.citations,
                },
                ui_element=answer.ui_element,
                attachments=list(
                    dict.fromkeys(
                        [
                            *(answer.attachments or []),
                            *([answer.attachment] if answer.attachment else []),
                        ]
                    )
                ),
            )
        self.db.audit("ask", f"trace={answer.trace_id[:12]} path={answer.path} intent={answer.intent} "
                             f"q={safe_q[:80]!r}")
        return answer

    def _store_trace(self, question: str, answer: Answer) -> None:
        steps = [{"name": s.name, "detail": redact_credentials(redact(s.detail)), "ms": round(s.ms, 2)} for s in answer.trace]
        self.db.add_trace({
            "trace_id": answer.trace_id, "ts": time.time(), "question": redact_credentials(redact(question)), "path": answer.path,
            "intent": answer.intent, "confidence": answer.confidence, "latency_ms": answer.latency_ms,
            "llm_calls": answer.llm_calls, "llm_tokens": answer.llm_tokens, "steps": json.dumps(steps)})

    def _agent(self, guardrails: bool) -> System2Agent:
        """One compiled LangGraph agent per configuration, reused across requests."""
        key = (guardrails, self.settings.agent_tools, self.settings.top_k, self.settings.max_agent_steps)
        if key not in self._agents:
            self._agents[key] = System2Agent(self.db, self.reasoner, self.engine, top_k=self.settings.top_k,
                                             max_steps=self.settings.max_agent_steps, guard_chunks=guardrails,
                                             use_tools=self.settings.agent_tools)
        return self._agents[key]

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

    def _handle(
        self,
        question: str,
        mode: Mode,
        guardrails: bool,
        tracer: Tracer,
        tau: float,
        *,
        history: list[dict[str, str]] | None = None,
        thread_id: str | None = None,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Answer:
        agent = self._agent(guardrails)
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

        # Counts are database facts, not a question for semantic search or the LLM. Returning
        # them directly avoids the model claiming it cannot tell how many indexed documents exist.
        if mode == "ours" and _is_whole_library_count(question):
            docs = self.db.list_documents()
            count = len(docs)
            text = f"There {'is' if count == 1 else 'are'} {count} document{'s' if count != 1 else ''} in your Smriti library."
            with tracer.span("s1.document_count") as s:
                s["detail"] = f"counted {count} indexed document(s)"
            return Answer(text=text, path="S1", intent="fact_lookup", confidence=1.0,
                          guard_verdicts=verdicts)

        if mode == "ours" and _is_greeting(question):
            text = (
                "Namaste! I am **Smriti**, your private academic assistant.\n\n"
                "I know your documents (exam datesheets, class timetables, marksheets, and past papers). "
                "Ask me about your exam schedule, marks/SGPA, or question paper topics!"
            )
            with tracer.span("s1.greeting") as s:
                s["detail"] = "conversational greeting handled directly by System 1"
            return Answer(text=text, path="S1", intent="other", confidence=1.0,
                          guard_verdicts=verdicts)

        inline_creds = _extract_samarth_credentials(question)
        effective_q = question
        hist = list(history or ())
        if hist and inline_creds is None:
            with tracer.span("s1.context") as s:
                effective_q = (
                    self.reasoner.contextualize(question, hist)
                    if hasattr(self.reasoner, "contextualize")
                    else contextualize_followup(question, hist)
                )
                if effective_q != question:
                    s["detail"] = (
                        f"window={len(hist)} msg(s); "
                        f"{redact_credentials(redact(question))!r} → {redact_credentials(redact(effective_q))!r}"
                    )
                else:
                    s["detail"] = f"window={len(hist)} msg(s) (standalone)"

        if mode == "ours" and _wants_live_timetable(effective_q, inline_creds is not None):
            return self._samarth_live_path("timetable", effective_q, inline_creds, tracer, verdicts)
        if mode == "ours" and _wants_live_attendance(effective_q, inline_creds is not None):
            return self._samarth_live_path("attendance", effective_q, inline_creds, tracer, verdicts)
        if mode == "ours" and _wants_pyq_analysis(effective_q, self.settings.pyq_dir):
            pyq_ans = self._pyq_analysis_path(effective_q, tracer, verdicts)
            if pyq_ans is not None:
                return pyq_ans
        if mode == "ours" and _wants_pyq_lookup(effective_q, self.settings.pyq_dir):
            return self._pyq_lookup_path(effective_q, tracer, verdicts)
        if mode == "ours" and _wants_syllabus_lookup(effective_q, self.settings.syllabus_dir):
            syl_ans = self._syllabus_lookup_path(effective_q, tracer, verdicts)
            if syl_ans is not None:
                return syl_ans

        with tracer.span("s1.router") as s:
            route = self.engine.route(effective_q)
            s["detail"] = f"{route.label} (p={route.probability:.2f})"

        if mode == "ours" and route.probability >= tau:
            fast = self._fast_path(effective_q, route.label, route.probability, tracer, tau)
            if fast is not None:
                fast.guard_verdicts = verdicts + fast.guard_verdicts
                return fast

        with tracer.span("escalate") as s:
            s["detail"] = f"to System 2 (intent={route.label}, p={route.probability:.2f}, " \
                          f"tau={tau})"
        emit_token = (lambda delta: on_event("token", {"delta": delta})) if on_event else None
        draft = agent.run(
            effective_q,
            tracer,
            intent=route.label,
            history=hist,
            thread_id=thread_id,
            raw_question=question,
            already_contextualized=bool(hist),
            on_token=emit_token,
            cancel_event=cancel_event,
        )
        verdicts += draft.verdicts
        text, citations = draft.text, draft.citations

        if guardrails:
            if draft.chunks:
                with tracer.span("s1.guard.grounding") as s:
                    g = self._ground(text, draft.chunks)
                    s["detail"] = f"{g.verdict.detail} (score={g.verdict.score:.2f})"
                if not g.verdict.passed:
                    if on_event:
                        on_event("reset", {})
                    with tracer.span("s2.retry") as s:
                        s["detail"] = "nothing grounded: searching wider and answering again"
                    draft = agent.run(
                        effective_q,
                        tracer,
                        intent=route.label,
                        widen=True,
                        history=hist,
                        thread_id=thread_id,
                        raw_question=question,
                        already_contextualized=True,
                        on_token=emit_token,
                        cancel_event=cancel_event,
                    )
                    with tracer.span("s1.guard.grounding") as s:
                        g = self._ground(draft.text, draft.chunks)
                        s["detail"] = f"{g.verdict.detail} (score={g.verdict.score:.2f})"
                if g.verdict.passed:
                    text, citations = g.text, cited_refs(g.text, draft.chunks)
                else:
                    if hasattr(self.reasoner, "answer_general"):
                        if on_event:
                            on_event("reset", {})
                        text = _call_reasoner(
                            self.reasoner.answer_general,
                            question,
                            history=hist or None,
                            on_token=emit_token,
                            cancel_event=cancel_event,
                        )
                        citations = []
                    else:
                        text, citations = IDK, []
                verdicts.append(g.verdict)
            else:
                with tracer.span("s1.guard.grounding") as s:
                    s["detail"] = "no matching documents (general knowledge fallback)"
                citations = []
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

    def _samarth_live_path(
        self,
        kind: str,  # "attendance" | "timetable"
        question: str,
        inline_creds: tuple[str, str] | None,
        tracer: Tracer,
        verdicts: list,
    ) -> Answer:
        roll, pwd = inline_creds if inline_creds else (None, None)
        if not inline_creds:
            saved = load_samarth_credentials(self.vault)
            if saved:
                roll, pwd = saved

        doc_title = "DCRUST Samarth Timetable" if kind == "timetable" else "DCRUST Samarth Attendance"
        span_name = "s1.samarth_timetable" if kind == "timetable" else "s1.samarth_attendance"
        wants_refresh = bool(
            re.search(r"\b(?:sync|refresh|live|fetch|update|samarth|esamarth)\b", question, re.IGNORECASE)
        )
        if not (roll and pwd):
            cached_doc = next((d for d in self.db.list_documents() if d["title"] == doc_title), None)
            if cached_doc and not wants_refresh:
                cached_chunks = self.db.document_chunks(cached_doc["id"])
                text = "\n\n".join(c.text for c in cached_chunks) if cached_chunks else f"No cached {kind} found."
                with tracer.span(span_name) as s:
                    s["detail"] = f"returned cached {kind} report"
                return Answer(text=text, citations=[f"{cached_doc['title']} p.1"], path="S1",
                              intent="fact_lookup", confidence=1.0, guard_verdicts=verdicts)
            with tracer.span(span_name) as s:
                s["detail"] = "missing eSamarth credentials"
            action_btn = "Samarth Timetable" if kind == "timetable" else "Samarth Attendance"
            slash = "/timetable" if kind == "timetable" else "/samarth"
            cli_cmd = "smriti timetable --login" if kind == "timetable" else "smriti attendance --login"
            prompt_ex = f"Check my {kind} roll no <ROLL_NO> password <PASSWORD>"
            hint = (
                f"To fetch your live {kind} from **DCRUST Samarth** (`dcrustm.samarth.edu.in`), "
                "please either:\n"
                f"- Click **{action_btn}** (or type `{slash}`) in the chat UI,\n"
                f"- Run `{cli_cmd}` in your terminal, or\n"
                f"- Ask in chat: `{prompt_ex}`."
            )
            return Answer(text=hint, path="S1", intent="fact_lookup", confidence=1.0, guard_verdicts=verdicts)

        with tracer.span(span_name) as s:
            try:
                if kind == "timetable":
                    report, html_path = sync_samarth_timetable(
                        self.db,
                        self.vault,
                        self.settings.data_dir,
                        roll_number=roll,
                        password=pwd,
                        save_creds=self.vault.unlocked,
                        client=self.samarth_client,
                    )
                    s["detail"] = f"fetched {len(report.weekly_slots)} slots, {len(report.events)} events for {report.roll_number}"
                    text = format_timetable_markdown(report)
                    ui_element = {"name": "DcrustTimetable", "props": timetable_to_ui_props(report)}
                else:
                    report, html_path = sync_samarth_attendance(
                        self.db,
                        self.vault,
                        self.settings.data_dir,
                        roll_number=roll,
                        password=pwd,
                        save_creds=self.vault.unlocked,
                        client=self.samarth_client,
                    )
                    s["detail"] = f"fetched {len(report.subjects)} subjects for {report.roll_number} ({report.overall_percentage_str})"
                    text = format_attendance_markdown(report)
                    ui_element = {"name": "DcrustAttendance", "props": attendance_to_ui_props(report)}
                return Answer(
                    text=text,
                    citations=[f"DCRUST Samarth ({report.roll_number})"],
                    path="S1",
                    intent="fact_lookup",
                    confidence=1.0,
                    attachment=str(html_path),
                    guard_verdicts=verdicts,
                    ui_element=ui_element,
                )
            except SamarthError as exc:
                s["detail"] = f"error: {exc}"
                return Answer(
                    text=f"⚠️ Could not fetch Samarth {kind}: {exc}",
                    path="S1",
                    intent="fact_lookup",
                    confidence=1.0,
                    guard_verdicts=verdicts,
                )

    def _pyq_analysis_path(self, question: str, tracer: Tracer, verdicts: list) -> Answer | None:
        with tracer.span("s1.pyq_analyze") as s:
            analysis = analyze_subject_pyqs(question, self.settings.pyq_dir)
            s["detail"] = (
                f"{analysis.subject_code}: {analysis.questions_extracted} question(s) across "
                f"{analysis.papers_analyzed} paper(s)"
                if analysis
                else "no matching downloaded PYQs for analysis"
            )
        if analysis is None:
            return None
        return Answer(
            text=analysis.markdown,
            citations=analysis.citations,
            path="S1",
            intent="exam_prep",
            confidence=1.0,
            attachments=analysis.attachments,
            guard_verdicts=verdicts,
        )

    def _pyq_lookup_path(self, question: str, tracer: Tracer, verdicts: list) -> Answer:
        pyq_dir = self.settings.pyq_dir
        with tracer.span("s1.pyq_lookup") as s:
            result = search_pyqs(question, pyq_dir)
            s["detail"] = (
                f"matched {len(result.matches)} subject(s), {result.total_papers} paper(s) for {result.cleaned_query!r}"
                if result.catalog_ready
                else "PYQ catalog not yet downloaded"
            )
        text = format_pyq_markdown(result, pyq_dir)
        if not result.matches:
            return Answer(
                text=text,
                path="S1",
                intent="fetch_doc",
                confidence=1.0,
                guard_verdicts=verdicts,
            )

        local_pdfs: list[str] = []
        for grp in result.matches:
            for e in grp.entries:
                if e.local_relpath:
                    p = pyq_dir / e.local_relpath
                    if p.exists():
                        local_pdfs.append(str(p))

        exports_dir = self.settings.data_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", result.cleaned_query or "pyqs").strip("_") or "pyqs"
        html_path = exports_dir / f"dcrust_pyqs_{slug[:40]}.html"
        html_path.write_text(format_pyq_html(result, pyq_dir), encoding="utf-8")

        return Answer(
            text=text,
            citations=[f"DCRUST EDP PYQ Catalog ({result.catalog_total_entries:,} papers)"],
            path="S1",
            intent="fetch_doc",
            confidence=1.0,
            attachment=str(html_path),
            attachments=local_pdfs[:12],
            guard_verdicts=verdicts,
            ui_element={"name": "DcrustPyqs", "props": pyq_to_ui_props(result, pyq_dir)},
        )

    def _syllabus_lookup_path(self, question: str, tracer: Tracer, verdicts: list) -> Answer | None:
        syllabus_dir = self.settings.syllabus_dir
        with tracer.span("s1.syllabus_lookup") as s:
            result = search_syllabus(question, syllabus_dir)
            s["detail"] = (
                f"matched {len(result.matches)} syllabus doc(s) "
                f"(branch={result.branch_id or 'any'}, year={result.year_id or 'any'})"
                if result.catalog_ready
                else "syllabus catalog not yet downloaded"
            )
        if result.catalog_ready and not result.matches and not (result.branch_id or result.year_id or result.degree):
            return None
        text = format_syllabus_markdown(result, syllabus_dir)
        if not result.matches:
            return Answer(
                text=text,
                path="S1",
                intent="fetch_doc",
                confidence=1.0,
                guard_verdicts=verdicts,
            )

        local_files: list[str] = []
        for e in result.matches:
            if e.local_relpath:
                p = syllabus_dir / e.local_relpath
                if p.exists():
                    local_files.append(str(p))

        exports_dir = self.settings.data_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{result.branch_id or 'all'}_{result.year_id or 'all'}").strip("_")
        html_path = exports_dir / f"dcrust_syllabus_{slug[:40]}.html"
        html_path.write_text(format_syllabus_html(result, syllabus_dir), encoding="utf-8")

        return Answer(
            text=text,
            citations=[f"DCRUST University Syllabus ({result.catalog_total_entries} schemes)"],
            path="S1",
            intent="fetch_doc",
            confidence=1.0,
            attachment=str(html_path),
            attachments=local_files[:10],
            guard_verdicts=verdicts,
            ui_element={"name": "DcrustSyllabus", "props": syllabus_to_ui_props(result, syllabus_dir)},
        )
