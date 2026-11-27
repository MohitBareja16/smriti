"""System 2 reasoners (LLM backends)."""

from smriti.config import Settings
from smriti.llm.base import Reasoner
from smriti.llm.extractive import ExtractiveReasoner, contextualize_followup, needs_contextualization
from smriti.llm.ollama import (
    LLMUnavailableError,
    OllamaReasoner,
    RequestCancelledError,
    list_ollama_models,
    ollama_status,
)


def get_reasoner(settings: Settings) -> Reasoner:
    if settings.llm_backend == "ollama":
        return OllamaReasoner(
            settings.llm_model,
            settings.ollama_url,
            num_ctx=settings.llm_num_ctx,
            max_tokens=settings.llm_max_tokens,
            keep_alive=settings.llm_keep_alive,
            num_threads=settings.llm_threads,
        )
    if settings.llm_backend == "extractive":
        return ExtractiveReasoner()
    raise ValueError(f"Unknown LLM backend '{settings.llm_backend}' (use 'ollama' or 'extractive').")


__all__ = [
    "ExtractiveReasoner",
    "LLMUnavailableError",
    "OllamaReasoner",
    "Reasoner",
    "RequestCancelledError",
    "contextualize_followup",
    "get_reasoner",
    "list_ollama_models",
    "needs_contextualization",
    "ollama_status",
]
