"""Local LLM through Ollama's HTTP API (stdlib only, no extra dependency)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Callable

from smriti.llm.base import ANSWER_SYSTEM, CONTEXTUALIZE_SYSTEM, GENERAL_SYSTEM, PLAN_SYSTEM, format_sources
from smriti.llm.extractive import contextualize_followup, needs_contextualization
from smriti.types import Chunk


class LLMUnavailableError(RuntimeError):
    pass


class RequestCancelledError(RuntimeError):
    """Raised when an active streamed LLM request is aborted by the caller."""


class OllamaReasoner:
    name = "ollama"

    def __init__(
        self,
        model: str,
        url: str = "http://localhost:11434",
        timeout: float = 180.0,
        *,
        num_ctx: int = 2048,
        max_tokens: int = 512,
        keep_alive: str = "15m",
        num_threads: int | None = None,
    ):
        self.model, self.url, self.timeout = model, url.rstrip("/"), timeout
        self.num_ctx = num_ctx
        self.max_tokens = max_tokens
        self.keep_alive = keep_alive
        self.num_threads = num_threads
        self.calls = 0
        self.tokens = 0  # prompt + completion tokens, for cost/latency research (RQ2)

    def _chat(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        history: list[dict[str, str]] | None = None,
        on_token: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        if cancel_event is not None and cancel_event.is_set():
            raise RequestCancelledError("Request cancelled")
        messages = [{"role": "system", "content": system}]
        for turn in history or ():
            role = turn.get("role")
            content = (turn.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user})
        streaming = on_token is not None
        options: dict[str, int | float] = {
            "temperature": 0,
            "num_ctx": self.num_ctx,
            "num_predict": self.max_tokens,
        }
        if self.num_threads is not None and self.num_threads > 0:
            options["num_thread"] = self.num_threads
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": streaming,
            "keep_alive": self.keep_alive,
            "options": options,
        }
        if json_mode:
            payload["format"] = "json"
        req = urllib.request.Request(f"{self.url}/api/chat", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        self.calls += 1
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if not streaming:
                    data = json.loads(resp.read())
                    self.tokens += int(data.get("prompt_eval_count", 0)) + int(data.get("eval_count", 0))
                    return data["message"]["content"].strip()

                parts: list[str] = []
                for raw_line in resp:
                    if cancel_event is not None and cancel_event.is_set():
                        raise RequestCancelledError("Request cancelled")
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    chunk = json.loads(line)
                    delta = chunk.get("message", {}).get("content") or ""
                    if delta:
                        parts.append(delta)
                        if on_token is not None:
                            on_token(delta)
                    if chunk.get("done"):
                        self.tokens += int(chunk.get("prompt_eval_count", 0)) + int(chunk.get("eval_count", 0))
                return "".join(parts).strip()
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            raise LLMUnavailableError(
                f"Could not reach Ollama model '{self.model}' at {self.url}. Is `ollama serve` running and "
                f"the model pulled (`ollama pull {self.model}`)? Or set SMRITI_LLM=extractive."
            ) from exc

    def contextualize(self, question: str, history: list[dict[str, str]]) -> str:
        if not history or not needs_contextualization(question):
            return question
        heuristic = contextualize_followup(question, history)
        hist_text = "\n".join(f"{t['role'].title()}: {t['content'][:300]}" for t in history[-4:])
        prompt = f"Conversation:\n{hist_text}\n\nLatest user message: {question}"
        try:
            rewritten = self._chat(CONTEXTUALIZE_SYSTEM, prompt).strip().strip('"').strip("'")
            return rewritten if 3 <= len(rewritten) <= 240 else heuristic
        except LLMUnavailableError:
            return heuristic

    def plan_queries(self, question: str) -> list[str]:
        raw = self._chat(PLAN_SYSTEM, question, json_mode=True)
        try:
            queries = [q for q in json.loads(raw).get("queries", []) if isinstance(q, str) and q.strip()]
        except (json.JSONDecodeError, AttributeError):
            queries = []
        return queries[:3] or [question]

    def answer(
        self,
        question: str,
        chunks: list[Chunk],
        *,
        history: list[dict[str, str]] | None = None,
        on_token: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        if not chunks:
            from smriti.guardrails import IDK

            return IDK
        user = f"Sources:\n{format_sources(chunks)}\n\nQuestion: {question}"
        return self._chat(
            ANSWER_SYSTEM, user, history=history, on_token=on_token, cancel_event=cancel_event
        )

    def answer_general(
        self,
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
        on_token: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        return self._chat(
            GENERAL_SYSTEM, question, history=history, on_token=on_token, cancel_event=cancel_event
        )


def list_ollama_models(url: str = "http://localhost:11434", timeout: float = 2.0) -> list[str]:
    """Return installed Ollama model tags from `/api/tags`, or [] when unreachable."""
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/tags", timeout=timeout) as resp:
            return [m["name"] for m in json.loads(resp.read()).get("models", []) if m.get("name")]
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return []


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
