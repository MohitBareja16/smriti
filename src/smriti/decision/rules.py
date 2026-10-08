"""Rules engine: a transparent, zero-dependency System-1 baseline.

It scores hand-written patterns and turns the scores into probabilities with a softmax, so it has
the same typed + confidence interface as learned engines. It is the baseline the learned engines
(SetFit, jeff) must beat.
"""

from __future__ import annotations

import math
import re

from smriti.decision.text import norm_set
from smriti.types import INTENTS, Decision

_I = re.IGNORECASE

ROUTE_PATTERNS: dict[str, list[tuple[re.Pattern[str], float]]] = {
    "fetch_doc": [
        (re.compile(r"\b(give|send|show|open|fetch|download|get)\b[^?]*\b(certificate|marksheet|grade card|"
                    r"document|pdf|file|copy|transcript|id card)\b", _I), 3.0),
    ],
    "fact_lookup": [
        (re.compile(r"^\s*(when|which date|how many|where is|what(?:'s| is| was| are) my)\b", _I), 1.5),
        (re.compile(r"\b(exam|date|cgpa|sgpa|marks?|grade|deadline|expiry|expires?|expire|issued|"
                    r"roll number|score|result|hall)\b", _I), 1.5),
    ],
    "compare": [
        (re.compile(r"\b(compare|comparison|difference|differ|versus|vs\.?|contrast)\b", _I), 3.0),
    ],
    "exam_prep": [
        (re.compile(r"\b(past papers?|previous years?|pyqs?|frequently|most asked|important topics|"
                    r"come up)\b", _I), 3.0),
    ],
    "connect": [
        (re.compile(r"\b(which|what)\b[^?]*\b(skills?|courses?|projects?|certificates?|certifications?|topics?)\b"
                    r"[^?]*\b(used|use|apply|applied|relates?|related|connect\w*|link\w*|in my projects)\b", _I), 3.0),
        (re.compile(r"\b(where have i used|in common|overlap|link between|connection between)\b", _I), 3.0),
    ],
    "explain": [
        (re.compile(r"^\s*(explain|describe|define|summari[sz]e|what (?:is|are) (?!my\b)|how (?:does|do)|why)",
                    _I), 2.0),
        (re.compile(r"\b(concept|algorithm|meaning of)\b", _I), 0.5),
    ],
}

INJECTION_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"\b(ignore|disregard|forget)\b[^.]{0,30}\b(previous|prior|above|earlier|all)\b[^.]{0,20}"
                r"\b(instructions?|prompts?|rules)\b", _I), 3.0),
    (re.compile(r"\bsystem prompt\b", _I), 2.0),
    (re.compile(r"\b(reveal|print|dump|leak|list|output)\b[^.]{0,30}\b(all|every)\b[^.]{0,30}"
                r"\b(aadhaar|ids?|passwords?|secrets?|keys?|personal data|documents)\b", _I), 2.5),
    (re.compile(r"\byou are now\b|\bdeveloper mode\b|\bdo anything now\b|\bjailbreak", _I), 2.5),
    (re.compile(r"\bpretend\b[^.]{0,30}\b(no|without)\b[^.]{0,20}\b(rules|restrictions|limits)\b", _I), 2.5),
    (re.compile(r"\b(send|email|upload|post|forward)\b[^.]{0,40}\bto\b[^.]{0,40}(https?://|@|\bserver\b)",
                _I), 2.5),
]

_SCALE = 1.5  # sharpens the softmax; tuned on the dev split


class RulesEngine:
    name = "rules"

    def route(self, question: str) -> Decision:
        scores = {intent: 0.0 for intent in INTENTS}
        scores["other"] = 1.0  # prior: when nothing matches, "other" wins
        for intent, patterns in ROUTE_PATTERNS.items():
            scores[intent] += sum(w for p, w in patterns if p.search(question))
        exps = {k: math.exp(_SCALE * v) for k, v in scores.items()}
        total = sum(exps.values())
        probs = {k: v / total for k, v in exps.items()}
        label = max(probs, key=probs.get)
        return Decision(label=label, probability=probs[label], probs=probs)

    def is_injection(self, text: str) -> Decision:
        score = sum(w for p, w in INJECTION_PATTERNS if p.search(text))
        p_yes = 1.0 - math.exp(-score) if score else 0.02
        label = "yes" if p_yes >= 0.5 else "no"
        return Decision(label=label, probability=p_yes if label == "yes" else 1 - p_yes,
                        probs={"yes": p_yes, "no": 1 - p_yes})

    def is_supported(self, claim: str, evidence: str) -> Decision:
        claim_toks = norm_set(claim)
        if not claim_toks:
            return Decision("yes", 1.0, {"yes": 1.0, "no": 0.0})
        covered = len(claim_toks & norm_set(evidence)) / len(claim_toks)
        label = "yes" if covered >= 0.6 else "no"
        return Decision(label=label, probability=covered if label == "yes" else 1 - covered,
                        probs={"yes": covered, "no": 1 - covered})
