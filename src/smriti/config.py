"""Settings, read from environment variables (prefix SMRITI_) with safe local defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(f"SMRITI_{name}", default)


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", "./data")))
    # LLM used by System 2. "ollama" (local, default) or "extractive" (no model, offline fallback).
    llm_backend: str = field(default_factory=lambda: _env("LLM", "ollama"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "qwen2.5:3b"))
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434"))
    # System 1 engine: "rules" (zero-dependency baseline). More engines are pluggable (see decision/).
    s1_engine: str = field(default_factory=lambda: _env("S1_ENGINE", "rules"))
    # Confidence threshold tau: System 1 answers alone only when p >= tau.
    tau_fast: float = field(default_factory=lambda: float(_env("TAU_FAST", "0.75")))
    # Minimum grounding score for a System 2 answer to be accepted.
    tau_grounding: float = field(default_factory=lambda: float(_env("TAU_GROUNDING", "0.5")))
    top_k: int = field(default_factory=lambda: int(_env("TOP_K", "5")))
    max_agent_steps: int = field(default_factory=lambda: int(_env("MAX_AGENT_STEPS", "2")))
    # Passphrase that unlocks the encrypted vault. Never commit it.
    passphrase: str | None = field(default_factory=lambda: os.environ.get("SMRITI_PASSPHRASE"))
    tracing: str = field(default_factory=lambda: _env("TRACING", "off"))  # "off" | "phoenix"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "smriti.db"

    @property
    def vault_dir(self) -> Path:
        return self.data_dir / "vault"

    def ensure_dirs(self) -> None:
        self.vault_dir.mkdir(parents=True, exist_ok=True)
