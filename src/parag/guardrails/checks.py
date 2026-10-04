"""Guardrails, all powered by System-1 decisions:

G1  input guard: prompt injection in the question, and in retrieved chunks
G2  grounding:   is each sentence of the answer supported by the cited sources?
G3  PII leak:    redact personal data the user did not ask for
"""

from __future__ import annotations

import re
from dataclasses import replace

from parag.decision.base import DecisionEngine
from parag.guardrails.pii import find_pii, redact, requested_pii_kinds
from parag.types import Chunk, GuardVerdict

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_LINE_OR_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_CITATION = re.compile(r"\[\d+(?:,\s*\d+)*\]")
IDK = "I don't know based on your documents."


def check_input(question: str, engine: DecisionEngine) -> GuardVerdict:
    d = engine.is_injection(question)
    return GuardVerdict("input", passed=d.label == "no", score=d.probs.get("yes", 0.0),
                        detail="prompt injection suspected" if d.label == "yes" else "safe")


def filter_chunks(chunks: list[Chunk], engine: DecisionEngine) -> tuple[list[Chunk], GuardVerdict]:
    """Strip injected instructions from retrieved chunks (documents are data, not commands).

    Only the offending sentences are removed, so the rest of a classmate's notes stays usable.
    """
    safe, flagged = [], []
    for c in chunks:
        if engine.is_injection(c.text).label == "no":
            safe.append(c)
            continue
        flagged.append(c.ref)
        kept = [s for s in _LINE_OR_SENTENCE.split(c.text) if engine.is_injection(s).label == "no"]
        cleaned = " ".join(s.strip() for s in kept if s.strip())
        if len(cleaned) > 40:
            safe.append(replace(c, text=cleaned))
    detail = f"stripped injected text from: {', '.join(flagged)}" if flagged else "no injected chunks"
    return safe, GuardVerdict("chunks", passed=not flagged, score=len(flagged) / max(len(chunks), 1),
                              detail=detail)


def check_grounding(answer: str, chunks: list[Chunk], engine: DecisionEngine,
                    threshold: float = 0.5) -> GuardVerdict:
    if answer.strip() == IDK or not answer.strip():
        return GuardVerdict("grounding", passed=True, score=1.0, detail="abstained")
    evidence = "\n".join(c.text for c in chunks)
    sentences = [s for s in (_CITATION.sub("", s).strip() for s in _SENTENCE.split(answer)) if len(s) > 3]
    if not sentences:
        return GuardVerdict("grounding", passed=False, score=0.0, detail="empty answer")
    supported = [engine.is_supported(s, evidence).label == "yes" for s in sentences]
    score = sum(supported) / len(sentences)
    return GuardVerdict("grounding", passed=score >= threshold, score=score,
                        detail=f"{sum(supported)}/{len(sentences)} sentences supported")


def check_pii(answer: str, question: str) -> tuple[str, GuardVerdict]:
    allowed = requested_pii_kinds(question)
    leaked = [m for m in find_pii(answer) if m.kind not in allowed]
    if not leaked:
        return answer, GuardVerdict("pii", passed=True, score=0.0, detail="no unrequested PII")
    kinds = sorted({m.kind for m in leaked})
    return redact(answer, keep=allowed), GuardVerdict("pii", passed=False, score=float(len(leaked)),
                                                      detail=f"redacted: {', '.join(kinds)}")
