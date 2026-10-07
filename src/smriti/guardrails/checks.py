"""Guardrails, all powered by System-1 decisions:

G1  input guard: prompt injection in the question, and in retrieved chunks
G2  grounding:   is each sentence of the answer supported by the sources? (drop or abstain)
G3  PII leak:    redact personal data the user did not ask for
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from smriti.decision.base import DecisionEngine
from smriti.decision.grounding import Grounder
from smriti.guardrails.pii import find_pii, redact, requested_pii_kinds
from smriti.types import Chunk, GuardVerdict

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


_CITE_AFTER_STOP = re.compile(r"([.!?])\s*((?:\[\d+(?:,\s*\d+)*\]\s*)+)")


def split_answer(answer: str) -> list[str]:
    """Split an answer into sentences, keeping each citation marker with its own sentence.

    "A is x. [1] B is y. [2]" -> ["A is x [1].", "B is y [2]."]
    """
    normalised = _CITE_AFTER_STOP.sub(lambda m: f" {m.group(2).strip()}{m.group(1)} ", answer)
    return [s.strip() for s in _SENTENCE.split(normalised.strip()) if s.strip()]


@dataclass
class GroundingResult:
    text: str
    verdict: GuardVerdict
    kept: int
    total: int


def ground_answer(answer: str, chunks: list[Chunk], grounder: Grounder, *, policy: str = "trim",
                  threshold: float = 0.5) -> GroundingResult:
    """G2: check every sentence of the answer against the retrieved chunks.

    policy="trim"     keep supported sentences, drop the rest; fail only if nothing is supported
    policy="abstain"  keep the whole answer if >= `threshold` of sentences are supported, else fail
    """
    if policy not in ("trim", "abstain"):
        raise ValueError("policy must be 'trim' or 'abstain'")
    if answer.strip() == IDK or not answer.strip():
        return GroundingResult(answer, GuardVerdict("grounding", True, 1.0, "abstained"), 0, 0)
    sentences = split_answer(answer)
    claims = [_CITATION.sub("", s).strip() for s in sentences]
    checkable = [i for i, c in enumerate(claims) if len(c) > 3]
    if not checkable:
        return GroundingResult(answer, GuardVerdict("grounding", False, 0.0, "empty answer"), 0, 0)
    decisions = grounder.check([claims[i] for i in checkable], [c.text for c in chunks])
    supported = {i for i, d in zip(checkable, decisions) if d.label == "yes"}
    score = len(supported) / len(checkable)
    detail = f"{len(supported)}/{len(checkable)} sentences supported ({grounder.name})"
    if policy == "abstain":
        return GroundingResult(answer, GuardVerdict("grounding", score >= threshold, score, detail),
                               len(checkable) if score >= threshold else 0, len(checkable))
    kept = [s for i, s in enumerate(sentences) if i in supported]
    if len(kept) < len(checkable):
        detail += f"; dropped {len(checkable) - len(kept)} unsupported"
    return GroundingResult(" ".join(kept), GuardVerdict("grounding", bool(kept), score, detail),
                           len(kept), len(checkable))


def check_grounding(answer: str, chunks: list[Chunk], grounder: Grounder | None = None,
                    threshold: float = 0.5) -> GuardVerdict:
    """Answer-level verdict (the 'abstain' policy). Kept for experiments and backward compatibility."""
    return ground_answer(answer, chunks, grounder or Grounder(), policy="abstain", threshold=threshold).verdict


def check_pii(answer: str, question: str) -> tuple[str, GuardVerdict]:
    allowed = requested_pii_kinds(question)
    leaked = [m for m in find_pii(answer) if m.kind not in allowed]
    if not leaked:
        return answer, GuardVerdict("pii", passed=True, score=0.0, detail="no unrequested PII")
    kinds = sorted({m.kind for m in leaked})
    return redact(answer, keep=allowed), GuardVerdict("pii", passed=False, score=float(len(leaked)),
                                                      detail=f"redacted: {', '.join(kinds)}")
