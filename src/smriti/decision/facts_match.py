"""Match a fact-lookup question to the facts table (System-1 direct answer)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from smriti.decision.text import norm_set
from smriti.types import Fact

_PARENS = re.compile(r"\([^)]*\)")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


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


def numbers(text: str) -> set[str]:
    """Numeric qualifiers in a text ("semester 04" -> {"4"}), used to detect conflicting facts."""
    return {n.lstrip("0") or "0" for n in _NUMBER.findall(text)}


def qualifiers_conflict(question: str, attribute: str) -> bool:
    """True when both mention numbers and none agree, e.g. 'semester 9' vs 'CGPA (after Semester 4)'.

    Word overlap alone can't see this, so without the check System 1 confidently answers with the
    wrong fact (docs/research/LOG.md, issue #10).
    """
    q, a = numbers(question), numbers(attribute)
    return bool(q and a and not (q & a))


def match_fact(question: str, facts: list[Fact]) -> FactMatch | None:
    q = norm_set(question, drop_generic=True)
    scored = sorted(((0.0 if qualifiers_conflict(question, f.attribute) else fact_score(q, f.attribute), f)
                     for f in facts), key=lambda x: -x[0])
    if not scored or scored[0][0] == 0:
        return None
    best_score, best = scored[0]
    # Two facts that match equally well = ambiguous, so System 1 should not answer alone.
    if len(scored) > 1 and scored[1][0] >= best_score - 1e-9:
        best_score *= 0.5
    return FactMatch(best, best_score)
