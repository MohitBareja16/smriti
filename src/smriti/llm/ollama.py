"""Local LLM through Ollama's HTTP API (stdlib only, no extra dependency)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from smriti.llm.base import ANSWER_SYSTEM, PLAN_SYSTEM, format_sources
from smriti.types import Chunk


class LLMUnavailableError(RuntimeError):
    pass


class OllamaReasoner:
    name = "ollama"

    def __init__(self, model: str, url: str = "http://localhost:11434", timeout: float = 180.0):
        self.model, self.url, self.timeout = model, url.rstrip("/"), timeout
        self.calls = 0

    def _chat(self, system: str, user: str, *, json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": 0},
        }
        if json_mode:
            payload["format"] = "json"
        req = urllib.request.Request(f"{self.url}/api/chat", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        self.calls += 1
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())["message"]["content"].strip()
        except (urllib.error.URLError, TimeoutError, KeyError) as exc:
            raise LLMUnavailableError(
                f"Could not reach Ollama model '{self.model}' at {self.url}. Is `ollama serve` running and "
                f"the model pulled (`ollama pull {self.model}`)? Or set SMRITI_LLM=extractive."
            ) from exc

    def plan_queries(self, question: str) -> list[str]:
        raw = self._chat(PLAN_SYSTEM, question, json_mode=True)
        try:
            queries = [q for q in json.loads(raw).get("queries", []) if isinstance(q, str) and q.strip()]
        except (json.JSONDecodeError, AttributeError):
            queries = []
        return queries[:3] or [question]

    def answer(self, question: str, chunks: list[Chunk]) -> str:
        if not chunks:
            from smriti.guardrails import IDK

            return IDK
        user = f"Sources:\n{format_sources(chunks)}\n\nQuestion: {question}"
        return self._chat(ANSWER_SYSTEM, user)


def ollama_status(model: str, url: str = "http://localhost:11434", timeout: float = 3.0) -> tuple[bool, str]:
    """Check whether Ollama is running and has `model`. Returns (ok, human-readable message)."""
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/tags", timeout=timeout) as resp:
            names = [m["name"] for m in json.loads(resp.read()).get("models", [])]
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False, "Ollama is not running (install it from https://ollama.com, then run `ollama serve`)."
    if any(n == model or n.split(":")[0] == model or n == f"{model}:latest" for n in names):
        return True, f"Using local model '{model}'."
    available = ", ".join(names) or "none"
    return False, f"Model '{model}' is not downloaded (run `ollama pull {model}`). Downloaded models: {available}."
