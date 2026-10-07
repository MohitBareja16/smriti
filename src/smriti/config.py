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
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "qwen2.5:3b"))
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434"))
    # System 1 engine: "rules" (zero-dependency baseline). More engines are pluggable (see decision/).
    s1_engine: str = field(default_factory=lambda: _env("S1_ENGINE", "rules"))
    # Confidence threshold tau: System 1 answers alone only when p >= tau.
    tau_fast: float = field(default_factory=lambda: float(_env("TAU_FAST", "0.75")))
    # G2 grounding check (issue #9). rule: lexical (no extra installs) | embedding | nli | hybrid.
    grounding: str = field(default_factory=lambda: _env("GROUNDING", "lexical"))
    # Threshold for the rule; empty = the rule's default (lexical 0.6, embedding 0.6, nli 0.5).
    grounding_threshold: float | None = field(
        default_factory=lambda: float(_env("GROUNDING_THRESHOLD", "")) if _env("GROUNDING_THRESHOLD", "") else None)
    # trim: drop unsupported sentences, abstain only if none are left | abstain: all-or-nothing.
    grounding_policy: str = field(default_factory=lambda: _env("GROUNDING_POLICY", "trim"))
    # For the 'abstain' policy: minimum share of supported sentences.
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
