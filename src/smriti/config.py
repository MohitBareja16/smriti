"""Settings, read from environment variables (prefix SMRITI_) with safe local defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(f"SMRITI_{name}", default)


HOME = Path("~/.smriti").expanduser()  # where your data lives by default
DEMO_DIR = HOME / "demo"                # the fictional demo student
DEMO_PASSPHRASE = "demo"                # demo data is fictional, so a fixed passphrase is fine


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(HOME / "data"))).expanduser())
    # LLM used by System 2. "ollama" (local, default) or "extractive" (no model, offline fallback).
    llm_backend: str = field(default_factory=lambda: _env("LLM", "ollama"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "qwen2.5:1.5b"))
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434"))
    # CPU-friendly Ollama inference budgets (tuned for smooth 8 GB RAM laptops without GPU).
    llm_num_ctx: int = field(default_factory=lambda: int(_env("LLM_NUM_CTX", "2048")))
    llm_max_tokens: int = field(default_factory=lambda: int(_env("LLM_MAX_TOKENS", "768")))
    llm_keep_alive: str = field(default_factory=lambda: _env("LLM_KEEP_ALIVE", "15m"))
    llm_threads: int | None = field(
        default_factory=lambda: int(_env("LLM_THREADS", "")) if _env("LLM_THREADS", "") else None
    )
    # Hybrid retrieval ("auto" uses cached local embeddings + BM25 RRF when available, else BM25).
    hybrid_search: str = field(default_factory=lambda: _env("HYBRID_SEARCH", "auto"))
    embed_model: str = field(default_factory=lambda: _env("EMBED_MODEL", "all-MiniLM-L6-v2"))
    # System 1 engine: "rules" (zero-dependency baseline). More engines are pluggable (see decision/).
    s1_engine: str = field(default_factory=lambda: _env("S1_ENGINE", "rules"))
    # Confidence threshold tau: System 1 answers alone only when p >= tau.
    tau_fast: float = field(default_factory=lambda: float(_env("TAU_FAST", "0.75")))
    # G2 grounding check (issue #9). auto = combined (lexical OR embedding) if the ml extra is
    # installed, else lexical. Also: lexical | combined | embedding | nli | hybrid.
    grounding: str = field(default_factory=lambda: _env("GROUNDING", "auto"))
    # Threshold for the rule; empty = the rule's default (lexical 0.6, embedding 0.6, nli 0.5).
    grounding_threshold: float | None = field(
        default_factory=lambda: float(_env("GROUNDING_THRESHOLD", "")) if _env("GROUNDING_THRESHOLD", "") else None)
    # trim: drop unsupported sentences, abstain only if none are left | abstain: all-or-nothing.
    grounding_policy: str = field(default_factory=lambda: _env("GROUNDING_POLICY", "trim"))
    # For the 'abstain' policy: minimum share of supported sentences.
    tau_grounding: float = field(default_factory=lambda: float(_env("TAU_GROUNDING", "0.5")))
    top_k: int = field(default_factory=lambda: int(_env("TOP_K", "5")))
    max_agent_steps: int = field(default_factory=lambda: int(_env("MAX_AGENT_STEPS", "2")))
    # Sliding-window multi-turn conversation memory bounds for System 2 + query contextualizer.
    context_turns: int = field(default_factory=lambda: int(_env("CONTEXT_TURNS", "6")))
    context_max_chars: int = field(default_factory=lambda: int(_env("CONTEXT_MAX_CHARS", "6000")))
    # System-2 tools chosen by System 1 per intent (#19). False = search only (+ graph for 'connect').
    agent_tools: bool = field(default_factory=lambda: _env("AGENT_TOOLS", "1") not in ("0", "false", "no"))
    # Passphrase that unlocks the encrypted vault. Never commit it.
    passphrase: str | None = field(default_factory=lambda: os.environ.get("SMRITI_PASSPHRASE"))
    tracing: str = field(default_factory=lambda: _env("TRACING", "off"))  # "off" | "phoenix"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "smriti.db"

    @property
    def vault_dir(self) -> Path:
        return self.data_dir / "vault"

    def _local_data_subdir(self, env_key: str, subdir: str) -> Path:
        override = os.environ.get(env_key)
        if override:
            return Path(override).expanduser()
        if self.data_dir == HOME / "data":
            repo_root = Path(__file__).resolve().parents[2]
            if (repo_root / "pyproject.toml").exists():
                return repo_root / subdir
        return self.data_dir / subdir

    @property
    def pyq_dir(self) -> Path:
        return self._local_data_subdir("SMRITI_PYQ_DIR", "pyqs")

    @property
    def syllabus_dir(self) -> Path:
        return self._local_data_subdir("SMRITI_SYLLABUS_DIR", "syllabus")

    def ensure_dirs(self) -> None:
        self.vault_dir.mkdir(parents=True, exist_ok=True)
