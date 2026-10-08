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
        self.tokens = 0  # prompt + completion tokens, for cost/latency research (RQ2)

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
                data = json.loads(resp.read())
            self.tokens += int(data.get("prompt_eval_count", 0)) + int(data.get("eval_count", 0))
            return data["message"]["content"].strip()
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


def warm_up(model: str, url: str = "http://localhost:11434", timeout: float = 600.0) -> float:
    """Load a model into memory with a tiny request. Returns the seconds it took (cold-start time)."""
    import time

    payload = {"model": model, "prompt": "Reply with OK.", "stream": False, "options": {"num_predict": 2}}
    req = urllib.request.Request(f"{url.rstrip('/')}/api/generate", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp.read()
    return time.perf_counter() - start


def unload(model: str, url: str = "http://localhost:11434") -> None:
    """Free the model's memory now (keep_alive=0) so the next model doesn't compete for RAM."""
    payload = {"model": model, "keep_alive": 0}
    req = urllib.request.Request(f"{url.rstrip('/')}/api/generate", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
    except (urllib.error.URLError, TimeoutError):
        pass
