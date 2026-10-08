"""Shared data types. `Answer` is the contract between all modules (see PRD §11)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Intent = Literal["fact_lookup", "fetch_doc", "explain", "compare", "exam_prep", "other"]
INTENTS: tuple[str, ...] = ("fact_lookup", "fetch_doc", "explain", "compare", "exam_prep", "other")


@dataclass
class Chunk:
    id: int
    doc_id: int
    doc_title: str
    page: int
    text: str
    course: str | None = None
    kind: str = "library"  # "library" | "personal"
    score: float = 0.0
    topic: str | None = None

    @property
    def ref(self) -> str:
        return f"{self.doc_title} p.{self.page}"


@dataclass
class Fact:
    attribute: str
    value: str
    doc_id: int
    doc_title: str
    page: int


@dataclass
class Decision:
    """A typed System-1 decision with calibrated-ish probabilities over labels."""

    label: str
    probability: float
    probs: dict[str, float] = field(default_factory=dict)


@dataclass
class GuardVerdict:
    guard: str  # "input" | "chunks" | "grounding" | "pii"
    passed: bool
    score: float
    detail: str = ""


@dataclass
class TraceStep:
    name: str
    detail: str
    ms: float = 0.0


@dataclass
class Answer:
    text: str
    citations: list[str] = field(default_factory=list)
    path: Literal["S1", "S2", "BLOCKED", "PLAIN"] = "S2"
    intent: str = "other"
    confidence: float = 0.0
    guard_verdicts: list[GuardVerdict] = field(default_factory=list)
    trace: list[TraceStep] = field(default_factory=list)
    llm_calls: int = 0
    llm_tokens: int = 0  # prompt + completion tokens reported by the LLM (0 for System 1)
    latency_ms: float = 0.0
    attachment: str | None = None  # path to a decrypted document for fetch_doc
    trace_id: str = ""  # OpenTelemetry trace id when tracing is on, else a random id
