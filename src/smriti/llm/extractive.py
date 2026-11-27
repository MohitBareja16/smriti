"""Offline fallback reasoner: no model, picks the best-matching sentences and cites them.

Useful for CI, for laptops without Ollama, and as a sanity baseline in the evals.
"""

from __future__ import annotations

import re

from smriti.decision.text import norm_set
from smriti.guardrails import IDK
from smriti.types import Chunk

_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_SPLIT = re.compile(r"\b(?:and|vs\.?|versus|with)\b", re.IGNORECASE)
_FOLLOWUP_CUE = re.compile(
    r"\b(?:it|its|they|them|their|he|his|him|she|her|hers|this|that|these|those|"
    r"same|there|what\s+about|how\s+about|and\s+for|what\s+of|more\s+about|else)\b",
    re.IGNORECASE,
)
_PRONOUN_SUB = re.compile(r"\b(?:it|its|they|them|their|he|his|him|she|her|this|that|those)\b", re.IGNORECASE)
_FOLLOWUP_PREFIX = re.compile(r"^\s*(?:and\s+)?(?:what|how)\s+about\s+", re.IGNORECASE)
_CODE_TOKEN = re.compile(r"\b([A-Z]{2,6}\d{2,4}[A-Z]{0,3})\b")


def needs_contextualization(question: str) -> bool:
    """True when a prompt looks like an anaphoric or elliptical follow-up."""
    q = (question or "").strip()
    if not q:
        return False
    if _FOLLOWUP_CUE.search(q):
        return True
    words = re.findall(r"[A-Za-z0-9]+", q)
    return len(words) <= 4 and q.endswith("?")


def contextualize_followup(question: str, history: list[dict[str, str]]) -> str:
    """Zero-LLM follow-up contextualizer resolving pronouns & short domain follow-ups."""
    if not history or not needs_contextualization(question):
        return question

    prev_users = [t["content"] for t in history if t.get("role") == "user" and t.get("content")]
    if not prev_users:
        return question
    last_user = prev_users[-1]

    # Carry domain forward for short follow-ups like "What about ECE?" or "And 2nd year?"
    if _FOLLOWUP_PREFIX.match(question) or len(re.findall(r"[A-Za-z0-9]+", question)) <= 5:
        stripped = _FOLLOWUP_PREFIX.sub("", question).strip(" ?.!").strip()
        stripped = re.sub(r"^(?:for|of|in|and)\s+", "", stripped, flags=re.IGNORECASE).strip()
        if stripped:
            last_low = last_user.lower()
            if re.search(r"\b(?:syllabus|syllabi)\b", last_low) and not re.search(r"\b(?:syllabus|syllabi|pyq|attendance|timetable)\b", stripped, re.IGNORECASE):
                from smriti.university.syllabus import extract_syllabus_filters

                b_new, y_new, d_new, _ = extract_syllabus_filters(stripped)
                b_old, y_old, d_old, _ = extract_syllabus_filters(last_user)
                parts = [stripped]
                if not b_new and b_old:
                    parts.append(b_old.replace("_", " "))
                if not y_new and y_old:
                    parts.append(f"{y_old} year")
                if not d_new and d_old:
                    parts.append(d_old)
                parts.append("syllabus")
                return " ".join(parts)
            if re.search(r"\b(?:pyqs?|pqps?|previous\s+year|past\s+papers?)\b", last_low) and not re.search(r"\b(?:pyqs?|pqps?|syllabus)\b", stripped, re.IGNORECASE):
                return f"Show PYQs for {stripped}"

    # Carry course code or primary topic nouns when pronouns appear ("What are its four conditions?")
    codes = _CODE_TOKEN.findall(last_user)
    if codes and _PRONOUN_SUB.search(question):
        return _PRONOUN_SUB.sub(codes[-1], question, count=1)

    topic_terms = [t for t in norm_set(last_user, drop_generic=True) if t not in norm_set(question)]
    if not topic_terms:
        # Try capitalized/key words from last_user directly (e.g. "Shah Rukh Khan", "Deadlock")
        proper = re.findall(r"\b[A-Z][a-zA-Z0-9]{2,}\b", last_user)
        topic_str = " ".join(dict.fromkeys(proper[-3:]))
    else:
        raw_words = re.findall(r"[A-Za-z0-9]{2,}", last_user)
        matched = [w for w in raw_words if next(iter(norm_set(w)), "") in set(topic_terms)]
        topic_str = " ".join(dict.fromkeys(matched[:3]))

    if not topic_str:
        return question
    if _PRONOUN_SUB.search(question):
        return _PRONOUN_SUB.sub(topic_str, question, count=1)
    return f"{question.rstrip(' ?.')} ({topic_str})"


class ExtractiveReasoner:
    name = "extractive"

    def __init__(self, max_sentences: int = 3, min_coverage: float = 0.34):
        self.max_sentences, self.min_coverage = max_sentences, min_coverage
        self.calls = 0
        self.tokens = 0

    def contextualize(self, question: str, history: list[dict[str, str]]) -> str:
        return contextualize_followup(question, history)

    def plan_queries(self, question: str) -> list[str]:
        parts = [p.strip() for p in _SPLIT.split(question) if len(p.strip()) > 3]
        return parts[:3] if len(parts) > 1 else [question]

    def answer(self, question: str, chunks: list[Chunk], *, history: list[dict[str, str]] | None = None) -> str:
        q = norm_set(question, drop_generic=True)
        if not q or not chunks:
            return IDK
        scored: list[tuple[float, int, str]] = []
        for i, c in enumerate(chunks, 1):
            for sent in _SENTENCE.split(c.text):
                sent = sent.strip(" -*#\t")
                if len(sent) < 20:
                    continue
                covered = len(q & norm_set(sent)) / len(q)
                if covered > 0:
                    scored.append((covered, i, sent))
        scored.sort(key=lambda x: -x[0])
        if scored and scored[0][0] >= self.min_coverage:
            picked = scored[: self.max_sentences]
            return " ".join(f"{s.rstrip('.')}. [{i}]" for _, i, s in picked)

        # When the user asks to summarize or inspect a named/just-uploaded document, return top sentences from its chunks
        q_low = question.lower()
        summary_req = bool(
            re.search(
                r"\b(?:summar\w*|overview|key\s+topics?|important\s+questions?|just\s+uploaded|uploaded\s+pdf|what\s+is\s+in)\b",
                q_low,
            )
        )
        title_hit = any(q & norm_set(c.doc_title) for c in chunks)
        if summary_req and (title_hit or "uploaded" in q_low or "just " in q_low):
            fallback: list[tuple[int, str]] = []
            for i, c in enumerate(chunks, 1):
                for sent in _SENTENCE.split(c.text):
                    s_clean = sent.strip(" -*#\t")
                    if len(s_clean) >= 20:
                        fallback.append((i, s_clean))
                        if len(fallback) >= self.max_sentences:
                            return " ".join(f"{s.rstrip('.')}. [{idx}]" for idx, s in fallback)
            if fallback:
                return " ".join(f"{s.rstrip('.')}. [{idx}]" for idx, s in fallback)
        return IDK

    def answer_general(self, question: str, *, history: list[dict[str, str]] | None = None) -> str:
        return IDK
