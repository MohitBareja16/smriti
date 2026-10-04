"""Offline fallback reasoner: no model, picks the best-matching sentences and cites them.

Useful for CI, for laptops without Ollama, and as a sanity baseline in the evals.
"""

from __future__ import annotations

import re

from parag.decision.text import norm_set
from parag.guardrails import IDK
from parag.types import Chunk

_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_SPLIT = re.compile(r"\b(?:and|vs\.?|versus|with)\b", re.IGNORECASE)


class ExtractiveReasoner:
    name = "extractive"

    def __init__(self, max_sentences: int = 3, min_coverage: float = 0.34):
        self.max_sentences, self.min_coverage = max_sentences, min_coverage
        self.calls = 0

    def plan_queries(self, question: str) -> list[str]:
        parts = [p.strip() for p in _SPLIT.split(question) if len(p.strip()) > 3]
        return parts[:3] if len(parts) > 1 else [question]

    def answer(self, question: str, chunks: list[Chunk]) -> str:
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
        if not scored or scored[0][0] < self.min_coverage:
            return IDK
        picked = scored[: self.max_sentences]
        return " ".join(f"{s.rstrip('.')}. [{i}]" for _, i, s in picked)
