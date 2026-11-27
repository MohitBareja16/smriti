"""FastAPI application factory wrapping SmritiApp for ChatGPT-style UI and HTTP/SSE clients."""

from __future__ import annotations

import asyncio
import json
import shutil
import threading
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pypdf.errors import FileNotDecryptedError, PdfReadError

from smriti.app import App, build_app
from smriti.config import DEMO_DIR
from smriti.graph import KnowledgeGraph
from smriti.ingest import ingest_file
from smriti.ingest.parsers import SUPPORTED, UnsupportedFileError
from smriti.llm import LLMUnavailableError, RequestCancelledError, get_reasoner, list_ollama_models
from smriti.server.files import file_view_url, is_allowed_file_path, media_type_for, serialize_attachments
from smriti.server.schemas import (
    ChatMessageOut,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    IndexFileRequest,
    ModelSelectRequest,
    SamarthSyncRequest,
    ThreadCreateRequest,
    ThreadDetail,
    ThreadRenameRequest,
    ThreadSummary,
    VaultUnlockRequest,
)
from smriti.university import (
    PyqSearchResult,
    PyqSubjectGroup,
    SamarthAuthError,
    SamarthError,
    SyllabusSearchResult,
    attendance_to_ui_props,
    clear_samarth_credentials,
    format_attendance_markdown,
    format_pyq_html,
    format_pyq_markdown,
    format_syllabus_html,
    format_syllabus_markdown,
    format_timetable_markdown,
    load_pyq_catalog,
    load_samarth_credentials,
    load_syllabus_catalog,
    pyq_to_ui_props,
    search_pyqs,
    search_syllabus,
    syllabus_to_ui_props,
    sync_samarth_attendance,
    sync_samarth_timetable,
    timetable_to_ui_props,
)
from smriti.vault import VaultLockedError, WrongPassphraseError


def _is_demo(app: App) -> bool:
    return app.settings.data_dir.resolve() == DEMO_DIR.resolve()


def _enrich_ui_element(ui_element: dict | None, app: App) -> dict | None:
    """Attach safe `/api/files/raw` local URLs onto custom UI element payloads."""
    if not ui_element:
        return None
    elem = json.loads(json.dumps(ui_element))
    name = elem.get("name")
    props = elem.get("props") or {}

    if name == "DcrustPyqs":
        pyq_dir = Path(props.get("pyqDir") or app.settings.pyq_dir)
        indexed_set = app.db.indexed_paths()
        for grp in props.get("groups", []):
            for paper in grp.get("papers", []):
                rel = paper.get("localRelpath")
                if paper.get("downloaded") and rel:
                    p = pyq_dir / rel
                    if is_allowed_file_path(p, app):
                        paper["localUrl"] = file_view_url(p)
                        paper["indexed"] = str(p.resolve()) in indexed_set
    elif name == "DcrustSyllabus":
        syl_dir = Path(props.get("syllabusDir") or app.settings.syllabus_dir)
        indexed_set = app.db.indexed_paths()
        for item in props.get("items", []):
            rel = item.get("localRelpath")
            if item.get("downloaded") and rel:
                p = syl_dir / rel
                if is_allowed_file_path(p, app):
                    item["localUrl"] = file_view_url(p)
                    item["indexed"] = str(p.resolve()) in indexed_set
    elif name == "DcrustAttendance":
        for subj in props.get("subjects", []):
            for lnk in subj.get("pyqLinks", []):
                u = lnk.get("url", "")
                if u and not u.startswith(("http://", "https://", "/api/")):
                    p = Path(u)
                    if is_allowed_file_path(p, app):
                        lnk["url"] = file_view_url(p)
    return elem


def _thread_summary(row) -> ThreadSummary:
    keys = row.keys()
    return ThreadSummary(
        id=row["id"],
        title=row["title"],
        message_count=int(row["message_count"]) if "message_count" in keys else 0,
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def _build_chat_response(answer, thread_id: str, thread_title: str, app: App) -> ChatResponse:
    raw_paths = list(getattr(answer, "attachments", []) or [])
    if answer.attachment and answer.attachment not in raw_paths:
        raw_paths.insert(0, answer.attachment)
    return ChatResponse(
        thread_id=thread_id,
        thread_title=thread_title,
        text=answer.text,
        citations=list(answer.citations),
        path=answer.path,
        intent=answer.intent,
        confidence=float(answer.confidence),
        llm_calls=int(answer.llm_calls),
        llm_tokens=int(answer.llm_tokens),
        latency_ms=float(answer.latency_ms),
        trace_id=answer.trace_id,
        trace=[{"name": s.name, "detail": s.detail, "ms": round(s.ms, 2)} for s in answer.trace],
        ui_element=_enrich_ui_element(answer.ui_element, app),
        attachments=serialize_attachments(raw_paths, app),
    )


def _sse_frame(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _iter_tokens(text: str, chunk_words: int = 4) -> Iterator[str]:
    tokens = text.splitlines(keepends=True)
    for line in tokens:
        if len(line) <= 48:
            yield line
            continue
        words = line.split(" ")
        for i in range(0, len(words), chunk_words):
            piece = " ".join(words[i : i + chunk_words])
            if i + chunk_words < len(words):
                piece += " "
            yield piece


def create_app(
    app_instance: App | None = None,
    *,
    static_dir: Path | None = None,
    demo_mode: bool | None = None,
) -> FastAPI:
    """Create the FastAPI app serving Smriti REST, SSE streaming, file preview, and optional UI bundle."""
    smriti_app = app_instance or build_app()
    is_demo_mode = _is_demo(smriti_app) if demo_mode is None else demo_mode
    lock = threading.RLock()

    api = FastAPI(title="Smriti AI API", version="0.2.0")
    api.state.smriti = smriti_app
    api.state.lock = lock

    api.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @api.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        with lock:
            docs = smriti_app.db.list_documents()
            threads = smriti_app.db.list_threads(limit=1000)
            samarth_saved = load_samarth_credentials(smriti_app.vault) is not None
        pyq_cat = load_pyq_catalog(smriti_app.settings.pyq_dir)
        syl_cat = load_syllabus_catalog(smriti_app.settings.syllabus_dir)
        return HealthResponse(
            demo_mode=is_demo_mode,
            vault_unlocked=smriti_app.vault.unlocked,
            llm_backend=smriti_app.settings.llm_backend,
            llm_model=smriti_app.settings.llm_model,
            document_count=len(docs),
            thread_count=len(threads),
            pyq_count=len(pyq_cat.entries) if pyq_cat else 0,
            syllabus_count=len(syl_cat.entries) if syl_cat else 0,
            samarth_saved=samarth_saved,
        )

    # ---- Threads / Recent Chats --------------------------------------------------------------
    @api.get("/api/threads", response_model=list[ThreadSummary])
    def list_threads(limit: int = Query(default=50, ge=1, le=200)) -> list[ThreadSummary]:
        with lock:
            rows = smriti_app.db.list_threads(limit=limit)
        return [_thread_summary(r) for r in rows]

    @api.post("/api/threads", response_model=ThreadSummary, status_code=201)
    def create_thread(req: ThreadCreateRequest | None = None) -> ThreadSummary:
        title = (req.title if req and req.title else "New Chat").strip() or "New Chat"
        with lock:
            tid = smriti_app.db.create_thread(title=title)
            row = smriti_app.db.get_thread(tid)
        return _thread_summary(row)

    @api.get("/api/threads/{thread_id}", response_model=ThreadDetail)
    def get_thread(thread_id: str) -> ThreadDetail:
        with lock:
            t_row = smriti_app.db.get_thread(thread_id)
            if t_row is None:
                raise HTTPException(status_code=404, detail="Thread not found")
            msg_rows = smriti_app.db.thread_messages(thread_id)
        messages: list[ChatMessageOut] = []
        for m in msg_rows:
            meta = json.loads(m["meta_json"] or "{}")
            ui_elem = json.loads(m["ui_element_json"]) if m["ui_element_json"] else None
            att_paths = json.loads(m["attachments_json"] or "[]")
            messages.append(
                ChatMessageOut(
                    id=int(m["id"]),
                    role=m["role"],
                    content=m["content"],
                    meta=meta,
                    ui_element=_enrich_ui_element(ui_elem, smriti_app),
                    attachments=serialize_attachments(att_paths, smriti_app),
                    created_at=float(m["created_at"]),
                )
            )
        summary = ThreadSummary(
            id=t_row["id"],
            title=t_row["title"],
            message_count=len(messages),
            created_at=float(t_row["created_at"]),
            updated_at=float(t_row["updated_at"]),
        )
        return ThreadDetail(thread=summary, messages=messages)

    @api.patch("/api/threads/{thread_id}", response_model=ThreadSummary)
    def rename_thread(thread_id: str, req: ThreadRenameRequest) -> ThreadSummary:
        clean = req.title.strip()
        if not clean:
            raise HTTPException(status_code=422, detail="Title cannot be blank")
        with lock:
            if not smriti_app.db.rename_thread(thread_id, clean):
                raise HTTPException(status_code=404, detail="Thread not found")
            rows = [r for r in smriti_app.db.list_threads(limit=200) if r["id"] == thread_id]
            row = rows[0] if rows else smriti_app.db.get_thread(thread_id)
        return _thread_summary(row)

    @api.delete("/api/threads/{thread_id}")
    def delete_thread(thread_id: str) -> dict:
        with lock:
            ok = smriti_app.db.delete_thread(thread_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Thread not found")
        return {"deleted": True, "thread_id": thread_id}

    # ---- Models & Chat / SSE Streaming -------------------------------------------------------
    def _apply_model(model_name: str | None) -> str:
        with lock:
            clean = (model_name or "").strip()
            if clean and smriti_app.settings.llm_backend == "ollama" and clean != smriti_app.settings.llm_model:
                smriti_app.settings.llm_model = clean
                smriti_app.orchestrator.reasoner = get_reasoner(smriti_app.settings)
                smriti_app.orchestrator._agents.clear()
            return smriti_app.settings.llm_model

    @api.get("/api/models")
    def list_models() -> dict:
        installed = (
            list_ollama_models(smriti_app.settings.ollama_url)
            if smriti_app.settings.llm_backend == "ollama"
            else []
        )
        recommended = ["qwen2.5:1.5b", "qwen2.5:3b", "qwen2.5:0.5b"]
        return {
            "backend": smriti_app.settings.llm_backend,
            "current": smriti_app.settings.llm_model,
            "installed": installed,
            "recommended": recommended,
        }

    @api.post("/api/models/select")
    async def select_model(req: ModelSelectRequest) -> dict:
        current = await asyncio.to_thread(_apply_model, req.model)
        return {"backend": smriti_app.settings.llm_backend, "current": current}

    def _run_chat_sync(req: ChatRequest) -> ChatResponse:
        q = req.question.strip()
        if not q:
            raise HTTPException(status_code=422, detail="Question cannot be empty")
        _apply_model(req.model)
        tid = req.thread_id or smriti_app.db.create_thread()
        if smriti_app.db.get_thread(tid) is None:
            smriti_app.db.create_thread(thread_id=tid)
        try:
            answer = smriti_app.orchestrator.handle(
                q, mode=req.mode, guardrails=req.guardrails, thread_id=tid
            )
        except LLMUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        t_row = smriti_app.db.get_thread(tid)
        title = t_row["title"] if t_row else "New Chat"
        return _build_chat_response(answer, tid, title, smriti_app)

    @api.post("/api/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest) -> ChatResponse:
        return await asyncio.to_thread(_run_chat_sync, req)

    @api.post("/api/chat/stream")
    async def chat_stream(req: ChatRequest) -> StreamingResponse:
        q = req.question.strip()
        if not q:
            raise HTTPException(status_code=422, detail="Question cannot be empty")

        async def event_gen():
            tid = req.thread_id or smriti_app.db.create_thread()
            if smriti_app.db.get_thread(tid) is None:
                smriti_app.db.create_thread(thread_id=tid)
            yield _sse_frame("thread", {"thread_id": tid})

            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()
            cancel_ev = threading.Event()

            def _emit(ev_name: str, payload: dict) -> None:
                loop.call_soon_threadsafe(queue.put_nowait, (ev_name, payload))

            def _worker() -> ChatResponse | None:
                try:
                    _apply_model(req.model)
                    answer = smriti_app.orchestrator.handle(
                        q,
                        mode=req.mode,
                        guardrails=req.guardrails,
                        thread_id=tid,
                        on_event=_emit,
                        cancel_event=cancel_ev,
                    )
                    t_row = smriti_app.db.get_thread(tid)
                    title = t_row["title"] if t_row else "New Chat"
                    return _build_chat_response(answer, tid, title, smriti_app)
                except RequestCancelledError:
                    return None
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            worker_task = asyncio.create_task(asyncio.to_thread(_worker))
            streamed_live_tokens = False
            try:
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=10.0)
                    except TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    if item is None:
                        break
                    ev_name, payload = item
                    if ev_name == "token":
                        streamed_live_tokens = True
                    elif ev_name == "reset":
                        streamed_live_tokens = False
                    yield _sse_frame(ev_name, payload)

                try:
                    resp = await worker_task
                except LLMUnavailableError as exc:
                    yield _sse_frame("error", {"status": 503, "detail": str(exc)})
                    return
                except HTTPException as exc:
                    yield _sse_frame("error", {"status": exc.status_code, "detail": exc.detail})
                    return
                except (RuntimeError, OSError, ValueError) as exc:
                    yield _sse_frame("error", {"status": 500, "detail": str(exc)})
                    return
                except Exception as exc:  # noqa: BLE001 — never drop an SSE stream without an error frame
                    yield _sse_frame("error", {"status": 500, "detail": f"{type(exc).__name__}: {exc}"})
                    return

                if resp is None:
                    return
                if not streamed_live_tokens:
                    for delta in _iter_tokens(resp.text):
                        yield _sse_frame("token", {"delta": delta})
                yield _sse_frame("done", resp.model_dump())
            finally:
                cancel_ev.set()

        return StreamingResponse(
            event_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ---- Vault & Documents -------------------------------------------------------------------
    @api.get("/api/vault/documents")
    def list_vault_documents() -> dict:
        with lock:
            docs = smriti_app.db.list_documents()
        return {
            "demo_mode": is_demo_mode,
            "vault_unlocked": smriti_app.vault.unlocked,
            "documents": [
                {
                    "id": int(d["id"]),
                    "title": d["title"],
                    "doc_type": d["doc_type"],
                    "kind": d["kind"],
                    "course": d["course"],
                    "semester": d["semester"],
                    "sensitive": bool(d["sensitive"]),
                    "created_at": float(d["created_at"]),
                }
                for d in docs
            ],
        }

    @api.post("/api/vault/upload")
    async def upload_vault_documents(files: Annotated[list[UploadFile], File(...)]) -> dict:
        if is_demo_mode:
            raise HTTPException(status_code=403, detail="Uploads are disabled in demo mode")
        document_dir = smriti_app.settings.data_dir / "documents"
        document_dir.mkdir(parents=True, exist_ok=True)
        results = []
        for upload in files:
            fname = Path(upload.filename or "document.txt").name
            suffix = Path(fname).suffix.lower()
            if suffix not in SUPPORTED:
                results.append({"name": fname, "ok": False, "error": f"Unsupported file type: {suffix}"})
                continue
            staged_dir = document_dir / uuid.uuid4().hex
            staged_dir.mkdir(parents=True, exist_ok=True)
            staged = staged_dir / fname
            try:
                content = await upload.read()
                staged.write_bytes(content)

                def _ingest_one(p: Path = staged):
                    with lock:
                        return ingest_file(p, smriti_app.db, smriti_app.vault)

                res = await asyncio.to_thread(_ingest_one)
                if res.sensitive or res.duplicate:
                    staged.unlink(missing_ok=True)
                    shutil.rmtree(staged_dir, ignore_errors=True)
                results.append(
                    {
                        "name": fname,
                        "ok": True,
                        "title": res.title,
                        "doc_type": res.doc_type,
                        "kind": res.kind,
                        "chunks": res.chunks,
                        "facts": res.facts,
                        "sensitive": res.sensitive,
                        "duplicate": res.duplicate,
                    }
                )
            except VaultLockedError as exc:
                shutil.rmtree(staged_dir, ignore_errors=True)
                results.append({"name": fname, "ok": False, "status": 423, "error": str(exc)})
            except (UnsupportedFileError, FileNotDecryptedError, PdfReadError, OSError, ValueError) as exc:
                shutil.rmtree(staged_dir, ignore_errors=True)
                results.append({"name": fname, "ok": False, "error": str(exc)})
        return {"results": results}

    @api.delete("/api/vault/documents/{doc_id}")
    def delete_vault_document(doc_id: int) -> dict:
        if is_demo_mode:
            raise HTTPException(status_code=403, detail="Deleting documents is disabled in demo mode")
        with lock:
            doc = smriti_app.db.get_document(doc_id)
            if doc is None:
                raise HTTPException(status_code=404, detail="Document not found")
            smriti_app.db.delete_document(doc_id)
            KnowledgeGraph(smriti_app.db).rebuild()
        return {"deleted": True, "id": doc_id}

    @api.post("/api/vault/unlock")
    def unlock_vault(req: VaultUnlockRequest) -> dict:
        with lock:
            try:
                smriti_app.vault.unlock(req.passphrase)
            except (VaultLockedError, WrongPassphraseError) as exc:
                raise HTTPException(status_code=401, detail=str(exc)) from exc
        return {"vault_unlocked": smriti_app.vault.unlocked}

    @api.post("/api/library/index-file")
    async def index_library_file(req: IndexFileRequest) -> dict:
        target = Path(req.path).expanduser()
        if not target.exists():
            raise HTTPException(status_code=404, detail="File not found")
        if not is_allowed_file_path(target, smriti_app):
            raise HTTPException(status_code=403, detail="Access denied outside approved Smriti directories")
        if target.suffix.lower() not in SUPPORTED:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {target.suffix}")

        def _do_index():
            with lock:
                return ingest_file(
                    target,
                    smriti_app.db,
                    smriti_app.vault,
                    course=req.course,
                    kind=req.kind,
                )

        try:
            res = await asyncio.to_thread(_do_index)
        except (UnsupportedFileError, FileNotDecryptedError, PdfReadError, OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ok": True,
            "doc_id": res.doc_id,
            "title": res.title,
            "doc_type": res.doc_type,
            "kind": res.kind,
            "chunks": res.chunks,
            "duplicate": res.duplicate,
        }

    # ---- Samarth / University Endpoints ------------------------------------------------------
    @api.get("/api/samarth/credentials")
    def samarth_credentials_status() -> dict:
        with lock:
            creds = load_samarth_credentials(smriti_app.vault)
        return {
            "saved": creds is not None,
            "roll_number": creds[0] if creds else None,
            "vault_unlocked": smriti_app.vault.unlocked,
        }

    @api.delete("/api/samarth/credentials")
    def samarth_credentials_clear() -> dict:
        with lock:
            removed = clear_samarth_credentials(smriti_app.vault)
        return {"cleared": removed}

    def _run_samarth_sync(kind: str, req: SamarthSyncRequest) -> dict:
        with lock:
            saved = load_samarth_credentials(smriti_app.vault)
            roll = (req.roll_number or "").strip() or (saved[0] if saved else None)
            pwd = req.password or (saved[1] if saved else None)
            if not (roll and pwd):
                raise HTTPException(status_code=400, detail="Missing eSamarth roll number or password")
            try:
                if kind == "timetable":
                    report, html_path = sync_samarth_timetable(
                        smriti_app.db,
                        smriti_app.vault,
                        smriti_app.settings.data_dir,
                        roll_number=roll,
                        password=pwd,
                        save_creds=req.save_creds and smriti_app.vault.unlocked,
                        client=smriti_app.orchestrator.samarth_client,
                    )
                    md = format_timetable_markdown(report)
                    ui_elem = {"name": "DcrustTimetable", "props": timetable_to_ui_props(report)}
                else:
                    report, html_path = sync_samarth_attendance(
                        smriti_app.db,
                        smriti_app.vault,
                        smriti_app.settings.data_dir,
                        roll_number=roll,
                        password=pwd,
                        save_creds=req.save_creds and smriti_app.vault.unlocked,
                        client=smriti_app.orchestrator.samarth_client,
                    )
                    md = format_attendance_markdown(report)
                    ui_elem = {"name": "DcrustAttendance", "props": attendance_to_ui_props(report)}
            except SamarthAuthError as exc:
                raise HTTPException(status_code=401, detail=str(exc)) from exc
            except SamarthError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc

            tid = req.thread_id
            if tid:
                smriti_app.db.add_chat_message(tid, "user", f"Sync Samarth {kind}")
                smriti_app.db.add_chat_message(
                    tid,
                    "assistant",
                    md,
                    meta={"path": "S1", "intent": "fact_lookup", "confidence": 1.0},
                    ui_element=ui_elem,
                    attachments=[str(html_path)],
                )

        return {
            "kind": kind,
            "thread_id": tid,
            "text": md,
            "ui_element": _enrich_ui_element(ui_elem, smriti_app),
            "attachments": serialize_attachments([str(html_path)], smriti_app),
        }

    @api.post("/api/samarth/attendance")
    async def samarth_attendance(req: SamarthSyncRequest) -> dict:
        return await asyncio.to_thread(_run_samarth_sync, "attendance", req)

    @api.post("/api/samarth/timetable")
    async def samarth_timetable(req: SamarthSyncRequest) -> dict:
        return await asyncio.to_thread(_run_samarth_sync, "timetable", req)

    @api.get("/api/pyqs/search")
    def pyq_search(
        q: str = Query(default="", max_length=200),
        limit: int = Query(default=24, ge=1, le=60),
    ) -> dict:
        pyq_dir = smriti_app.settings.pyq_dir
        clean_q = q.strip()
        if clean_q:
            result = search_pyqs(clean_q, pyq_dir, max_subjects=limit)
        else:
            cat = load_pyq_catalog(pyq_dir)
            if cat is None or not cat.entries:
                result = PyqSearchResult(
                    raw_query="",
                    cleaned_query="",
                    matches=[],
                    total_papers=0,
                    catalog_total_entries=0,
                    catalog_ready=False,
                )
            else:
                grouped: dict[str, list] = {}
                for e in cat.entries:
                    grouped.setdefault(e.course_code, []).append(e)
                groups = []
                for code, items in grouped.items():
                    sorted_items = sorted(items, key=lambda x: (-x.session_sort, x.session_label))
                    visible = [i for i in sorted_items if i.status != "missing_remote"] or sorted_items
                    subj_name = next((i.subject_name for i in visible if i.subject_name), code)
                    groups.append(
                        PyqSubjectGroup(
                            course_code=code,
                            subject_name=subj_name,
                            score=float(sum(1 for i in visible if i.status == "downloaded")),
                            entries=visible,
                        )
                    )
                groups.sort(key=lambda g: (-g.score, -len(g.entries), g.course_code))
                top_groups = groups[:limit]
                result = PyqSearchResult(
                    raw_query="",
                    cleaned_query="",
                    matches=top_groups,
                    total_papers=sum(len(g.entries) for g in top_groups),
                    catalog_total_entries=len(cat.entries),
                    catalog_ready=True,
                )

        props = pyq_to_ui_props(result, pyq_dir)
        ui_elem = _enrich_ui_element({"name": "DcrustPyqs", "props": props}, smriti_app)
        local_paths = [
            str(pyq_dir / e.local_relpath)
            for grp in result.matches
            for e in grp.entries
            if e.local_relpath and (pyq_dir / e.local_relpath).exists()
        ]
        exports_dir = smriti_app.settings.data_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        html_path = exports_dir / "dcrust_pyqs_latest.html"
        if result.matches:
            html_path.write_text(format_pyq_html(result, pyq_dir), encoding="utf-8")
            local_paths.insert(0, str(html_path))
        return {
            "text": format_pyq_markdown(result, pyq_dir),
            "catalog_ready": result.catalog_ready,
            "catalog_total_entries": result.catalog_total_entries,
            "total_papers": result.total_papers,
            "ui_element": ui_elem,
            "attachments": serialize_attachments(local_paths[:13], smriti_app),
        }

    @api.get("/api/syllabus/search")
    def syllabus_search(
        q: str = Query(default="", max_length=200),
        branch: str = Query(default="", max_length=40),
        year: str = Query(default="", max_length=20),
        limit: int = Query(default=100, ge=1, le=250),
    ) -> dict:
        syl_dir = smriti_app.settings.syllabus_dir
        clean_q = q.strip()
        if clean_q and not branch and not year:
            result = search_syllabus(clean_q, syl_dir, limit=limit)
        else:
            cat = load_syllabus_catalog(syl_dir)
            if cat is None or not cat.entries:
                result = SyllabusSearchResult(
                    raw_query=clean_q,
                    branch_id=branch or None,
                    branch_label=None,
                    year_id=year or None,
                    year_label=None,
                    degree=None,
                    matches=[],
                    catalog_total_entries=0,
                    catalog_ready=False,
                )
            else:
                pool = list(cat.entries)
                if branch:
                    pool = [
                        e
                        for e in pool
                        if e.department_id == branch
                        or (year == "1st" and e.department_id == "common_1st")
                    ]
                if year:
                    pool = [
                        e
                        for e in pool
                        if e.year_id == year or year in e.covered_years or e.year_id == "complete"
                    ]
                if clean_q:
                    terms = [t for t in clean_q.lower().split() if t]
                    pool = [
                        e
                        for e in pool
                        if all(
                            t in f"{e.title} {e.department_label} {e.degree} {e.year_label}".lower()
                            for t in terms
                        )
                    ]
                pool.sort(key=lambda e: (e.department_label, e.year_id, -e.session_sort, e.title.lower()))
                matches = pool[:limit]
                result = SyllabusSearchResult(
                    raw_query=clean_q,
                    branch_id=branch or None,
                    branch_label=matches[0].department_label if branch and matches else None,
                    year_id=year or None,
                    year_label=matches[0].year_label if year and matches else None,
                    degree=None,
                    matches=matches,
                    catalog_total_entries=len(cat.entries),
                    catalog_ready=True,
                )
        props = syllabus_to_ui_props(result, syl_dir)
        ui_elem = _enrich_ui_element({"name": "DcrustSyllabus", "props": props}, smriti_app)
        local_paths = [
            str(syl_dir / e.local_relpath)
            for e in result.matches
            if e.local_relpath and (syl_dir / e.local_relpath).exists()
        ]
        exports_dir = smriti_app.settings.data_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        html_path = exports_dir / "dcrust_syllabus_latest.html"
        if result.matches:
            html_path.write_text(format_syllabus_html(result, syl_dir), encoding="utf-8")
            local_paths.insert(0, str(html_path))
        return {
            "text": format_syllabus_markdown(result, syl_dir),
            "catalog_ready": result.catalog_ready,
            "catalog_total_entries": result.catalog_total_entries,
            "total_matched": len(result.matches),
            "ui_element": ui_elem,
            "attachments": serialize_attachments(local_paths[:11], smriti_app),
        }

    # ---- Safe Inline File Serving ------------------------------------------------------------
    @api.get("/api/files/raw")
    def serve_file(path: str = Query(..., min_length=1)) -> FileResponse:
        target = Path(path)
        if not target.expanduser().exists():
            raise HTTPException(status_code=404, detail="File not found")
        with lock:
            allowed = is_allowed_file_path(target, smriti_app)
        if not allowed:
            raise HTTPException(status_code=403, detail="Access denied outside approved Smriti directories")
        resolved = target.expanduser().resolve()
        return FileResponse(
            path=str(resolved),
            media_type=media_type_for(resolved),
            headers={"Content-Disposition": f'inline; filename="{resolved.name}"'},
        )

    # ---- Optional Built Frontend Static Mount (Phase 3) --------------------------------------
    if static_dir and (static_dir / "index.html").is_file():
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            api.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @api.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            candidate = (static_dir / full_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(static_dir.resolve()):
                return FileResponse(str(candidate))
            return FileResponse(str(static_dir / "index.html"))

    return api
