"""Match a fact-lookup question to the facts table (System-1 direct answer)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from parag.decision.text import norm_set
from parag.types import Fact

_PARENS = re.compile(r"\([^)]*\)")


@dataclass
class FactMatch:
    fact: Fact
    score: float  # 0..1, already penalised for ambiguity


def fact_score(question_tokens: set[str], attribute: str) -> float:
    """How well a fact's attribute answers the question.

    recall: share of the question's words found in the attribute (incl. qualifiers in parentheses)
    precision: share of the attribute's main words (outside parentheses) that the question mentions
    """
    if not question_tokens:
        return 0.0
    full, main = norm_set(attribute), norm_set(_PARENS.sub(" ", attribute)) or norm_set(attribute)
    recall = len(question_tokens & full) / len(question_tokens)
    precision = len(question_tokens & main) / len(main) if main else 0.0
    return recall * (0.6 + 0.4 * precision)


def match_fact(question: str, facts: list[Fact]) -> FactMatch | None:
    q = norm_set(question, drop_generic=True)
    scored = sorted(((fact_score(q, f.attribute), f) for f in facts), key=lambda x: -x[0])
    if not scored or scored[0][0] == 0:
        return None
    best_score, best = scored[0]
    # Two facts that match equally well = ambiguous, so System 1 should not answer alone.
    if len(scored) > 1 and scored[1][0] >= best_score - 1e-9:
        best_score *= 0.5
    return FactMatch(best, best_score)
