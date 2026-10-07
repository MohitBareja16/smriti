"""Chainlit chat UI that shows the thinking: every System-1 decision and System-2 step appears as a step.

Run:  chainlit run src/smriti/ui/chainlit_app.py
"""

from __future__ import annotations

import chainlit as cl

from smriti.app import build_app
from smriti.llm import LLMUnavailableError

BADGES = {"S1": "⚡ **System 1** (fast, no LLM)", "S2": "🧠 **System 2** (agent)", "BLOCKED": "🛡 **Blocked**",
          "PLAIN": "Plain RAG"}

_app = None


def get_app():
    global _app
    if _app is None:
        _app = build_app()
    return _app


@cl.on_chat_start
async def start() -> None:
    app = get_app()
    docs = app.db.list_documents()
    offline = ("\n\n> Offline mode: no local LLM found, so answers quote your documents directly. "
               "For full answers install [Ollama](https://ollama.com) and run `ollama pull qwen2.5:3b`."
               if app.settings.llm_backend == "extractive" else "")
    hint = "" if docs else "\n\nYou haven't added any documents yet. In a terminal, run `smriti add <folder>`."
    await cl.Message(
        content=f"Namaste! I am **Smriti**, and I know **{len(docs)} documents**. "
                "Ask about your notes, books, exams or certificates.\n\n"
                "Try: *When is my DBMS exam?* · *Explain deadlock from my OS notes* · "
                f"*Compare paging and segmentation*{hint}{offline}"
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
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
            f"LLM calls {answer.llm_calls} · {answer.latency_ms:.0f} ms")
    sources = f"\n\n**Sources:** {'; '.join(answer.citations)}" if answer.citations else ""
    elements = [cl.File(name=answer.attachment.split("/")[-1], path=answer.attachment)] \
        if answer.attachment and answer.path == "S1" and "exports" in answer.attachment else []
    await cl.Message(content=f"{answer.text}{sources}\n\n---\n{meta}", elements=elements).send()
