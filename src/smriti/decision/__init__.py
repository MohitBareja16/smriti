"""System 1: fast, typed, calibrated decisions."""

from smriti.decision.base import DecisionEngine
from smriti.decision.facts_match import FactMatch, match_fact
from smriti.decision.rules import RulesEngine

ENGINES = {"rules": RulesEngine}


def get_engine(name: str) -> DecisionEngine:
    try:
        return ENGINES[name]()
    except KeyError:
        raise ValueError(f"Unknown System-1 engine '{name}'. Available: {', '.join(ENGINES)}") from None


__all__ = ["DecisionEngine", "FactMatch", "RulesEngine", "get_engine", "match_fact"]
