"""System 2 reasoners (LLM backends)."""

from parag.config import Settings
from parag.llm.base import Reasoner
from parag.llm.extractive import ExtractiveReasoner
from parag.llm.ollama import LLMUnavailableError, OllamaReasoner


def get_reasoner(settings: Settings) -> Reasoner:
    if settings.llm_backend == "ollama":
        return OllamaReasoner(settings.llm_model, settings.ollama_url)
    if settings.llm_backend == "extractive":
        return ExtractiveReasoner()
    raise ValueError(f"Unknown LLM backend '{settings.llm_backend}' (use 'ollama' or 'extractive').")


__all__ = ["ExtractiveReasoner", "LLMUnavailableError", "OllamaReasoner", "Reasoner", "get_reasoner"]
