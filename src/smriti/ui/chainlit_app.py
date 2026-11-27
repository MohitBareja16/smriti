"""Chainlit chat UI that shows the thinking: every System-1 decision and System-2 step appears as a step.

Run:  chainlit run src/smriti/ui/chainlit_app.py
"""

from __future__ import annotations

import asyncio
import shutil
import threading
import uuid
from pathlib import Path

import chainlit as cl
from pypdf.errors import FileNotDecryptedError

from smriti.app import build_app
from smriti.config import DEMO_DIR
from smriti.ingest import ingest_file
from smriti.ingest.parsers import SUPPORTED, UnsupportedFileError
from smriti.llm import LLMUnavailableError
from smriti.vault import VaultLockedError

BADGES = {"S1": "⚡ **System 1** (fast, no LLM)", "S2": "🧠 **System 2** (agent)", "BLOCKED": "🛡 **Blocked**",
          "PLAIN": "Plain RAG"}

_app = None
_DB_LOCK = threading.RLock()
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


def _is_demo_app(app) -> bool:
    return app.settings.data_dir.resolve() == DEMO_DIR.resolve()


def _copy_and_ingest(source: Path, staged: Path, app):
    # The same SQLite connection serves chats and uploads; serialize worker-thread access.
    with _DB_LOCK:
        shutil.copyfile(source, staged)
        return ingest_file(staged, app.db, app.vault)


def _answer_question(question: str, thread_id: str | None = None):
    with _DB_LOCK:
        return get_app().orchestrator.handle(question, thread_id=thread_id)


def _vault_panel() -> cl.Message:
    app = get_app()
    with _DB_LOCK:
        docs = app.db.list_documents()
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
        f"Documents are indexed in your local library at `{app.settings.data_dir}` and "
        "stay available in future sessions. Personal documents are encrypted when a vault passphrase is set."
    )
    actions = [
        cl.Action(name="vault_upload", payload={}, label="Add document", icon="file-plus-2"),
        cl.Action(name="samarth_attendance", payload={}, label="Samarth Attendance", icon="calendar-check"),
        cl.Action(name="samarth_timetable", payload={}, label="Samarth Timetable", icon="calendar-days"),
        cl.Action(name="vault_refresh", payload={}, label="Refresh", icon="refresh-cw"),
    ]
    return cl.Message(content=content, actions=actions)


async def _upload_to_vault() -> None:
    if _is_demo_app(get_app()):
        await cl.Message(content="Uploads are disabled in demo mode. Restart with smriti ui to add your own documents.").send()
        return
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
    if _is_demo_app(app):
        await cl.Message(content="Uploads are disabled in demo mode. Restart with smriti ui to add your own documents.").send()
        return
    stored = []
    errors = []
    document_dir = app.settings.data_dir / "documents"
    await asyncio.to_thread(document_dir.mkdir, parents=True, exist_ok=True)
    for upload in uploads:
        suffix = Path(upload.name).suffix.lower()
        if suffix not in SUPPORTED:
            errors.append(f"{upload.name}: unsupported file type")
            try:
                Path(upload.path).unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"{upload.name}: could not remove temporary upload copy: {exc}")
            continue
        staged_dir = document_dir / uuid.uuid4().hex
        staged = staged_dir / Path(upload.name).name
        try:
            await asyncio.to_thread(staged_dir.mkdir)
            result = await asyncio.to_thread(_copy_and_ingest, Path(upload.path), staged, app)
            state = "already in the vault" if result.duplicate else f"{result.chunks} chunks indexed"
            stored.append(f"**{result.title}** — {state}")
            # Sensitive originals have already been encrypted. Keep durable sources only for
            # ordinary library files, whose paths are used by the document retrieval flow.
            if result.sensitive or result.duplicate:
                staged.unlink(missing_ok=True)
                staged_dir.rmdir()
        except (UnsupportedFileError, VaultLockedError, FileNotDecryptedError, OSError, ValueError) as exc:
            staged.unlink(missing_ok=True)
            try:
                staged_dir.rmdir()
            except OSError:
                pass
            errors.append(f"{upload.name}: {exc}")
        finally:
            try:
                Path(upload.path).unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"{upload.name}: could not remove temporary upload copy: {exc}")

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


async def _fetch_samarth_ui(kind: str = "attendance") -> None:
    from smriti.university import (
        SamarthError,
        attendance_to_ui_props,
        load_samarth_credentials,
        sync_samarth_attendance,
        sync_samarth_timetable,
        timetable_to_ui_props,
    )

    app = get_app()
    saved = load_samarth_credentials(app.vault)
    roll, pwd = saved if saved else (None, None)

    if not (roll and pwd):
        r_msg = await cl.AskUserMessage(
            content="Enter your **DCRUST eSamarth Roll Number** (e.g. `23001001065`):",
            timeout=180,
        ).send()
        if not r_msg or not r_msg.get("output", "").strip():
            await cl.Message(content=f"Cancelled Samarth {kind} check.").send()
            return
        p_msg = await cl.AskUserMessage(
            content="Enter your **Samarth Portal Password** (encrypted in your vault if unlocked; never stored in logs):",
            timeout=180,
        ).send()
        if not p_msg or not p_msg.get("output", "").strip():
            await cl.Message(content=f"Cancelled Samarth {kind} check.").send()
            return
        roll = r_msg["output"].strip()
        pwd = p_msg["output"].strip()

    def _run_sync():
        with _DB_LOCK:
            fn = sync_samarth_timetable if kind == "timetable" else sync_samarth_attendance
            return fn(
                app.db,
                app.vault,
                app.settings.data_dir,
                roll_number=roll,
                password=pwd,
                save_creds=app.vault.unlocked,
            )

    try:
        report, html_path = await asyncio.to_thread(_run_sync)
    except SamarthError as exc:
        await cl.Message(content=f"⚠️ Could not fetch Samarth {kind}: {exc}").send()
        return

    if kind == "timetable":
        elem = cl.CustomElement(name="DcrustTimetable", props=timetable_to_ui_props(report), display="inline")
        summary = f"Synced **{report.semester_label}** timetable ({len(report.weekly_slots)} weekly slots, {len(report.events)} sessions) for `{report.roll_number}`."
        badge = "⚡ **System 1** (DCRUST Samarth Timetable & Calendar · HTML export also attached)"
    else:
        elem = cl.CustomElement(name="DcrustAttendance", props=attendance_to_ui_props(report), display="inline")
        summary = f"Synced **{report.semester_label}** attendance (**{report.overall_percentage_str}**, `{report.total_attended} / {report.total_classes}`) for `{report.roll_number}`."
        badge = "⚡ **System 1** (DCRUST Samarth Attendance · HTML export also attached)"
    elements = [elem, cl.File(name=html_path.name, path=str(html_path))]
    await cl.Message(content=f"{summary}\n\n---\n{badge}", elements=elements).send()
    await _vault_panel().send()


@cl.action_callback("samarth_attendance")
async def samarth_attendance(_action: cl.Action) -> None:
    await _fetch_samarth_ui("attendance")


@cl.action_callback("samarth_timetable")
async def samarth_timetable(_action: cl.Action) -> None:
    await _fetch_samarth_ui("timetable")


@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="Samarth Timetable & Calendar",
            message="Show my Samarth timetable and calendar",
        ),
        cl.Starter(
            label="Samarth Attendance (75% Rule)",
            message="Check my Samarth attendance",
        ),
        cl.Starter(
            label="Semester Results (CGPA / SGPA)",
            message="What was my CGPA after semester 6?",
        ),
        cl.Starter(
            label="DCRUST PYQs (Subject Search)",
            message="Show all PYQs for CSE302C",
        ),
    ]


@cl.on_chat_start
async def start() -> None:
    app = get_app()
    with _DB_LOCK:
        docs = app.db.list_documents()
        thread_id = app.db.create_thread()
    cl.user_session.set("thread_id", thread_id)
    offline = ("\n\n> Offline mode: no local LLM found, so answers quote your documents directly. "
               "For full answers install [Ollama](https://ollama.com) and run `ollama pull qwen2.5:0.5b`."
               if app.settings.llm_backend == "extractive" else "")
    hint = "" if docs else "\n\nYou haven't added any documents yet. In a terminal, run `smriti add <folder>`."
    await cl.Message(
        content=f"Namaste! I am **Smriti**, your private local-first AI memory with **{len(docs)} documents** indexed.\n\n"
                "Ask about your **marksheets, exam datesheets, study notes, PYQs**, or sync live **DCRUST Samarth Attendance & Timetable** using the buttons below."
                f"{hint}{offline}"
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
    if message.content.strip().lower() in {"/attendance", "attendance", "/samarth", "samarth"}:
        await _fetch_samarth_ui("attendance")
        return
    if message.content.strip().lower() in {"/timetable", "timetable", "/calendar", "calendar"}:
        await _fetch_samarth_ui("timetable")
        return
    if message.content.strip().lower().startswith("/pyq"):
        raw_q = message.content.strip()[4:].strip()
        if not raw_q:
            await cl.Message(content="Enter a subject code or name, e.g. `/pyq CSE302C` or `/pyq Compiler Design`.").send()
            return
        message.content = f"Show PYQs for {raw_q}"
    if message.content.strip().lower().startswith("/syllabus"):
        raw_q = message.content.strip()[9:].strip()
        if not raw_q:
            await cl.Message(content="Enter branch and year, e.g. `/syllabus CSE 3rd year` or `/syllabus ECE 2nd year`.").send()
            return
        message.content = f"Show syllabus for {raw_q}"
    try:
        thread_id = cl.user_session.get("thread_id")
        answer = await asyncio.to_thread(_answer_question, message.content, thread_id)
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
    elements = []
    body_text = answer.text
    if answer.ui_element:
        elements.append(
            cl.CustomElement(
                name=answer.ui_element["name"],
                props=answer.ui_element["props"],
                display="inline",
            )
        )
        first_line = answer.text.splitlines()[0].lstrip("# ").strip() if answer.text else "Synced from DCRUST Samarth"
        body_text = f"**{first_line}**"
    if answer.attachment and answer.path == "S1" and "exports" in answer.attachment:
        elements.append(cl.File(name=answer.attachment.split("/")[-1], path=answer.attachment))
    for p in getattr(answer, "attachments", []) or []:
        if Path(p).exists():
            elements.append(cl.File(name=Path(p).name, path=p))
    await cl.Message(content=f"{body_text}{sources}\n\n---\n{meta}", elements=elements).send()
