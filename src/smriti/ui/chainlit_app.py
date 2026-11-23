"""Chainlit chat UI that shows the thinking: every System-1 decision and System-2 step appears as a step.

Run:  chainlit run src/smriti/ui/chainlit_app.py
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import chainlit as cl

from smriti.app import build_app
from smriti.ingest import ingest_file
from smriti.ingest.parsers import SUPPORTED, UnsupportedFileError
from smriti.llm import LLMUnavailableError
from smriti.vault import VaultLockedError

BADGES = {"S1": "⚡ **System 1** (fast, no LLM)", "S2": "🧠 **System 2** (agent)", "BLOCKED": "🛡 **Blocked**",
          "PLAIN": "Plain RAG"}

_app = None
_UPLOAD_TYPES = {
    "application/pdf": [".pdf"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    "text/markdown": [".md"],
    "text/plain": [".txt"],
}


def get_app():
    global _app
    if _app is None:
        _app = build_app()
    return _app


def _vault_panel() -> cl.Message:
    docs = get_app().db.list_documents()
    rows = [
        f"| {doc['title']} | {doc['doc_type'].replace('_', ' ').title()} | "
        f"{'Personal · encrypted' if doc['sensitive'] else 'Library'} |"
        for doc in docs
    ]
    listing = "\n".join(rows) if rows else "| Your vault is empty | — | — |"
    content = (
        f"### 🗄️ Your vault · {len(docs)} document{'s' if len(docs) != 1 else ''}\n\n"
        "| Document | Type | Stored as |\n|---|---|---|\n"
        f"{listing}\n\n"
        f"Documents are indexed in your local library at `{get_app().settings.data_dir}` and "
        "stay available in future sessions. Personal documents are encrypted when a vault passphrase is set."
    )
    actions = [
        cl.Action(name="vault_upload", payload={}, label="Add document", icon="file-plus-2"),
        cl.Action(name="vault_refresh", payload={}, label="Refresh", icon="refresh-cw"),
    ]
    return cl.Message(content=content, actions=actions)


async def _upload_to_vault() -> None:
    uploads = await cl.AskFileMessage(
        content="Choose PDF, Word, Markdown, or text documents to add to your local vault.",
        accept=_UPLOAD_TYPES,
        max_size_mb=100,
        max_files=10,
        timeout=300,
    ).send()
    if not uploads:
        await cl.Message(content="No files selected. Your vault is unchanged.").send()
        return

    await _store_uploads(uploads)


async def _store_uploads(uploads) -> None:
    app = get_app()
    stored = []
    errors = []
    document_dir = app.settings.data_dir / "documents"
    document_dir.mkdir(parents=True, exist_ok=True)
    for upload in uploads:
        suffix = Path(upload.name).suffix.lower()
        if suffix not in SUPPORTED:
            errors.append(f"{upload.name}: unsupported file type")
            continue
        staged_dir = document_dir / uuid.uuid4().hex
        staged_dir.mkdir()
        staged = staged_dir / Path(upload.name).name
        try:
            shutil.copyfile(upload.path, staged)
            result = ingest_file(staged, app.db, app.vault)
            state = "already in the vault" if result.duplicate else f"{result.chunks} chunks indexed"
            stored.append(f"**{result.title}** — {state}")
            # Sensitive originals have already been encrypted. Keep durable sources only for
            # ordinary library files, whose paths are used by the document retrieval flow.
            if result.sensitive or result.duplicate:
                staged.unlink(missing_ok=True)
                staged_dir.rmdir()
        except (UnsupportedFileError, VaultLockedError, OSError, ValueError) as exc:
            staged.unlink(missing_ok=True)
            staged_dir.rmdir()
            errors.append(f"{upload.name}: {exc}")

    if stored:
        await cl.Message(content="Added to your vault:\n\n" + "\n".join(f"- {item}" for item in stored)).send()
    if errors:
        await cl.Message(content="Some files could not be added:\n\n" + "\n".join(f"- {item}" for item in errors)).send()
    await _vault_panel().send()


@cl.action_callback("vault_upload")
async def vault_upload(_action: cl.Action) -> None:
    await _upload_to_vault()


@cl.action_callback("vault_refresh")
async def vault_refresh(_action: cl.Action) -> None:
    await _vault_panel().send()


@cl.on_chat_start
async def start() -> None:
    app = get_app()
    docs = app.db.list_documents()
    offline = ("\n\n> Offline mode: no local LLM found, so answers quote your documents directly. "
               "For full answers install [Ollama](https://ollama.com) and run `ollama pull qwen2.5:0.5b`."
               if app.settings.llm_backend == "extractive" else "")
    hint = "" if docs else "\n\nYou haven't added any documents yet. In a terminal, run `smriti add <folder>`."
    await cl.Message(
        content=f"Namaste! I am **Smriti**, and I know **{len(docs)} documents**. "
                "Ask about your notes, books, exams or certificates.\n\n"
                "Try: *When is my DBMS exam?* · *Explain deadlock from my OS notes* · "
                f"*Compare paging and segmentation*{hint}{offline}"
    ).send()
    await _vault_panel().send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    if message.elements:
        await _store_uploads(message.elements)
        return
    if message.content.strip().lower() in {"/vault", "vault"}:
        await _vault_panel().send()
        return
    try:
        answer = await cl.make_async(get_app().orchestrator.handle)(message.content)
    except LLMUnavailableError as exc:
        await cl.Message(content=f"⚠️ {exc}").send()
        return

    path_label = {"S1": "System 1", "S2": "System 1 → System 2", "BLOCKED": "System 1 guard",
                  "PLAIN": "plain RAG"}[answer.path]
    n = len(answer.trace)
    async with cl.Step(name=f"Thinking · {path_label} · {n} step{'s' if n != 1 else ''}", type="tool") as s:
        rows = "\n".join(f"| `{st.name}` | {st.detail.replace('|', '/')} | {st.ms:.0f} |" for st in answer.trace)
        s.output = f"| Step | Decision / detail | ms |\n|---|---|---|\n{rows}"

    meta = (f"{BADGES[answer.path]} · intent `{answer.intent}` · confidence {answer.confidence:.2f} · "
            f"LLM calls {answer.llm_calls} · {answer.latency_ms:.0f} ms · trace `{answer.trace_id[:12]}`")
    sources = f"\n\n**Sources:** {'; '.join(answer.citations)}" if answer.citations else ""
    elements = [cl.File(name=answer.attachment.split("/")[-1], path=answer.attachment)] \
        if answer.attachment and answer.path == "S1" and "exports" in answer.attachment else []
    await cl.Message(content=f"{answer.text}{sources}\n\n---\n{meta}", elements=elements).send()
