"""Pydantic v2 schemas for Smriti HTTP & SSE APIs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    demo_mode: bool
    vault_unlocked: bool
    llm_backend: str
    llm_model: str
    document_count: int
    thread_count: int
    pyq_count: int
    syllabus_count: int
    samarth_saved: bool


class ThreadCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class ThreadRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ThreadSummary(BaseModel):
    id: str
    title: str
    message_count: int
    created_at: float
    updated_at: float


class AttachmentItem(BaseModel):
    name: str
    path: str
    url: str
    ext: str
    sizeBytes: int = 0


class TraceStepOut(BaseModel):
    name: str
    detail: str
    ms: float


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    thread_id: str | None = None
    mode: Literal["ours", "agent", "plain"] = "ours"
    guardrails: bool = True
    model: str | None = Field(default=None, max_length=120)


class ChatResponse(BaseModel):
    thread_id: str
    thread_title: str
    text: str
    citations: list[str] = Field(default_factory=list)
    path: str
    intent: str
    confidence: float
    llm_calls: int
    llm_tokens: int
    latency_ms: float
    trace_id: str
    trace: list[TraceStepOut] = Field(default_factory=list)
    ui_element: dict | None = None
    attachments: list[AttachmentItem] = Field(default_factory=list)


class ChatMessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    meta: dict = Field(default_factory=dict)
    ui_element: dict | None = None
    attachments: list[AttachmentItem] = Field(default_factory=list)
    created_at: float


class ThreadDetail(BaseModel):
    thread: ThreadSummary
    messages: list[ChatMessageOut] = Field(default_factory=list)


class SamarthSyncRequest(BaseModel):
    roll_number: str | None = Field(default=None, max_length=64)
    password: str | None = Field(default=None, max_length=128)
    save_creds: bool = True
    thread_id: str | None = None


class VaultUnlockRequest(BaseModel):
    passphrase: str = Field(min_length=1, max_length=256)


class ModelSelectRequest(BaseModel):
    model: str = Field(min_length=1, max_length=120)


class IndexFileRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    course: str | None = Field(default=None, max_length=64)
    kind: Literal["library", "personal"] | None = None
