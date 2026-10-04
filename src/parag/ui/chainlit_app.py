"""Chainlit chat UI that shows the thinking: every System-1 decision and System-2 step appears as a step.

Run:  chainlit run src/parag/ui/chainlit_app.py
"""

from __future__ import annotations

import chainlit as cl

from parag.app import build_app
from parag.llm import LLMUnavailableError

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
    docs = get_app().db.list_documents()
    await cl.Message(
        content=f"Hi! I know **{len(docs)} documents**. Ask about your notes, books, exams or certificates.\n\n"
                "Try: *When is my DBMS exam?* · *Explain deadlock from my OS notes* · "
                "*Compare paging and segmentation*"
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    try:
        answer = await cl.make_async(get_app().orchestrator.handle)(message.content)
    except LLMUnavailableError as exc:
        await cl.Message(content=f"⚠️ {exc}").send()
        return

    for step in answer.trace:
        async with cl.Step(name=step.name, type="tool") as s:
            s.output = f"{step.detail}  ·  {step.ms:.0f} ms"

    meta = (f"{BADGES[answer.path]} · intent `{answer.intent}` · confidence {answer.confidence:.2f} · "
            f"LLM calls {answer.llm_calls} · {answer.latency_ms:.0f} ms")
    sources = f"\n\n**Sources:** {'; '.join(answer.citations)}" if answer.citations else ""
    elements = [cl.File(name=answer.attachment.split('/')[-1], path=answer.attachment)] \
        if answer.attachment and answer.path == "S1" and "exports" in answer.attachment else []
    await cl.Message(content=f"{answer.text}{sources}\n\n<sub>{meta}</sub>", elements=elements).send()
