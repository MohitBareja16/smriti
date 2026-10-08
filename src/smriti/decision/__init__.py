"""System 1: fast, typed, calibrated decisions."""

from pathlib import Path

from smriti.decision.base import DecisionEngine
from smriti.decision.facts_match import FactMatch, match_fact
from smriti.decision.rules import RulesEngine


def _embedding_engine() -> DecisionEngine:
    """The saved embedding router (smriti train-router), trained on first use if missing."""
    from smriti.decision.learned import EmbeddingRouter, default_model_path, training_data

    path = default_model_path()
    if path.exists():
        return EmbeddingRouter.load(path)
    data = Path(__file__).resolve().parents[3] / "evals" / "data"
    router = EmbeddingRouter().fit(*training_data(data))
    router.save(path)
    return router


def _zeroshot_engine() -> DecisionEngine:
    from smriti.decision.learned import ZeroShotRouter

    return ZeroShotRouter()


ENGINES = {"rules": RulesEngine, "embedding": _embedding_engine, "zeroshot": _zeroshot_engine}


def get_engine(name: str) -> DecisionEngine:
    try:
        return ENGINES[name]()
    except KeyError:
        raise ValueError(f"Unknown System-1 engine '{name}'. Available: {', '.join(ENGINES)}") from None


__all__ = ["DecisionEngine", "FactMatch", "RulesEngine", "get_engine", "match_fact"]
