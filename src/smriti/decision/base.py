"""System 1 interface: fast, typed decisions with a confidence score.

Every engine (rules, SetFit, jeff, ...) implements this protocol, so engines can be swapped and
compared in the evals (RQ5) without touching the rest of the system.
"""

from __future__ import annotations

from typing import Protocol

from smriti.types import Decision


class DecisionEngine(Protocol):
    name: str

    def route(self, question: str) -> Decision:
        """Classify the question's intent (see `smriti.types.INTENTS`) with a probability."""

    def is_injection(self, text: str) -> Decision:
        """Label 'yes' if the text tries to override instructions or extract secrets."""

    def is_supported(self, claim: str, evidence: str) -> Decision:
        """Label 'yes' if the claim is supported by the evidence text."""
