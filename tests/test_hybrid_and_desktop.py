from __future__ import annotations

import io
import json
import threading
import urllib.request

import pytest

from smriti.agent.system2 import System2Agent
from smriti.decision import get_engine
from smriti.desktop import _configure_environment, default_data_dir, open_browser_quietly, pick_port
from smriti.llm.ollama import OllamaReasoner, RequestCancelledError
from smriti.observability import Tracer
from smriti.storage import Database, LocalEmbedder


def _fake_encode(texts: list[str]) -> list[list[float]]:
    vecs = []
    for t in texts:
        low = t.lower()
        # Axis 0: scheduling/memory concepts; Axis 1: compiler concepts
        os_score = 1.0 if any(k in low for k in ("circular", "banker", "deadlock", "avoidance")) else 0.0
        comp_score = 1.0 if any(k in low for k in ("lexical", "parser", "syntax", "grammar")) else 0.0
        vecs.append([os_score, comp_score, 0.1])
    return vecs


def test_hybrid_search_rrf_and_backfill(tmp_path):
    db = Database(tmp_path / "hybrid.db")
    d1 = db.add_document(
        title="OS Lecture", path="/tmp/os.md", sha256="h1", kind="library",
        doc_type="notes", course="CSE301", sensitive=False, vault_file=None, semester=5,
    )
    d2 = db.add_document(
        title="Compiler Lecture", path="/tmp/cd.md", sha256="h2", kind="library",
        doc_type="notes", course="CSE302C", sensitive=False, vault_file=None, semester=6,
    )
    # Inserted before embedder is attached
    db.add_chunks(d1, [(1, "Banker algorithm prevents unsafe allocation states.")])
    db.add_chunks(d2, [(1, "Lexical grammar tokenizes source programs.")])

    embedder = LocalEmbedder(encode_fn=_fake_encode)
    db.attach_embedder(embedder)
    assert db.backfill_embeddings() == 2
    assert db.backfill_embeddings() == 0

    # Pure semantic query ("circular" has 0 keyword overlap with d1, yet matches via vector axis 0)
    hits = db.search("circular wait condition", k=3)
    assert hits and hits[0].doc_title == "OS Lecture"

    # Course metadata filter keeps semantic search strictly scoped
    filtered = db.search("circular wait condition", k=3, course="CSE302C")
    assert all(c.course == "CSE302C" for c in filtered)


def test_ollama_cpu_options_and_cancellation(monkeypatch):
    captured: list[dict] = []
    lines = [
        json.dumps({"message": {"content": "Part 1 "}, "done": False}).encode() + b"\n",
        json.dumps({"message": {"content": "Part 2"}, "done": False}).encode() + b"\n",
    ]

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            return iter(lines)

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda req, timeout=None: captured.append(json.loads(req.data.decode("utf-8"))) or FakeResp(b""),
    )
    cancel_ev = threading.Event()
    ollama = OllamaReasoner(model="qwen2.5:1.5b", num_ctx=2048, max_tokens=256, keep_alive="15m")

    def on_tok(_tok: str):
        cancel_ev.set()  # abort immediately after first chunk

    with pytest.raises(RequestCancelledError):
        ollama.answer_general("Explain paging", on_token=on_tok, cancel_event=cancel_ev)

    assert captured[0]["keep_alive"] == "15m"
    assert captured[0]["options"]["num_ctx"] == 2048
    assert captured[0]["options"]["num_predict"] == 256


def test_system2_skips_llm_planning_on_simple_queries(tmp_path):
    db = Database(tmp_path / "p.db")
    doc = db.add_document(
        title="OS", path="/tmp/os.md", sha256="s1", kind="library",
        doc_type="notes", course=None, sensitive=False, vault_file=None,
    )
    db.add_chunks(doc, [(1, "Paging divides memory into fixed-size frames.")])

    class SpyReasoner:
        name = "spy"
        calls = 0
        plan_calls = 0

        def contextualize(self, q, h):
            return q

        def plan_queries(self, q):
            self.plan_calls += 1
            return [q]

        def answer(self, q, chunks, *, history=None, on_token=None):
            self.calls += 1
            return "Paging divides memory [1]."

    spy = SpyReasoner()
    agent = System2Agent(db, spy, get_engine("rules"))
    agent.run("Explain paging", Tracer(), intent="other")
    assert spy.plan_calls == 0

    agent.run("Compare paging vs segmentation in OS", Tracer(), intent="compare")
    assert spy.plan_calls == 1


def test_desktop_bundle_helpers(tmp_path, monkeypatch):
    import os
    import shutil
    import subprocess
    import sys

    port = pick_port("127.0.0.1", preferred=48100, max_tries=10)
    assert 48100 <= port < 48110
    (tmp_path / ".portable").write_text("", encoding="utf-8")
    d = default_data_dir(tmp_path)
    assert d == tmp_path / "data" and d.is_dir()

    spawned = {}
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/xdg-open")
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda cmd, **kw: spawned.update(cmd=cmd, stdout=kw.get("stdout"), stderr=kw.get("stderr")) or None,
    )
    open_browser_quietly("http://127.0.0.1:8000")
    assert spawned["cmd"] == ["/usr/bin/xdg-open", "http://127.0.0.1:8000"]
    assert spawned["stdout"] is subprocess.DEVNULL and spawned["stderr"] is subprocess.DEVNULL

    opened_win: list[str] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "startfile", lambda url: opened_win.append(url), raising=False)
    open_browser_quietly("http://127.0.0.1:8000")
    assert opened_win == ["http://127.0.0.1:8000"]

    # Bundled offline tools (portable ollama.exe, models, hf_cache, tesseract) configure offline env cleanly
    (tmp_path / "ollama").mkdir()
    (tmp_path / "ollama" / "ollama.exe").write_bytes(b"MZ")
    (tmp_path / "models").mkdir()
    (tmp_path / "hf_cache").mkdir()
    (tmp_path / "tesseract" / "tessdata").mkdir(parents=True)
    for k in ("SMRITI_OLLAMA_URL", "HF_HOME", "SENTENCE_TRANSFORMERS_HOME", "HF_HUB_OFFLINE", "TESSDATA_PREFIX"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PATH", "")
    _configure_environment(tmp_path, tmp_path, demo=False)
    import os

    assert os.environ["SMRITI_OLLAMA_URL"].startswith("http://127.0.0.1:114")
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["SENTENCE_TRANSFORMERS_HOME"] == str(tmp_path / "hf_cache")
    assert os.environ["TESSDATA_PREFIX"] == str(tmp_path / "tesseract" / "tessdata")
    assert str(tmp_path / "tesseract") in os.environ["PATH"]


def test_coderabbit_hardening_regression(tmp_path, monkeypatch):
    import io

    from smriti.app import Settings, build_app
    from smriti.ingest import ingest_file
    from smriti.llm import LLMUnavailableError
    from smriti.llm.ollama import OllamaReasoner
    from smriti.university.pyq import (
        DcrustPyqClient,
        PyqCatalog,
        PyqEntry,
        parse_exam_sessions,
        save_pyq_catalog,
        sync_dcrust_pyqs,
    )
    from smriti.university.syllabus import SyllabusCatalog, classify_syllabus_item, search_syllabus
    from smriti.university.timetable import (
        build_timetable_report,
        format_timetable_html,
        timetable_to_ui_props,
    )

    # 1. Embeddings inference failure degrades cleanly instead of crashing
    broken = LocalEmbedder(encode_fn=lambda _texts: (_ for _ in ()).throw(RuntimeError("oom")))
    assert broken.encode_many(["paging"]) == []
    assert broken.encode_one("paging") is None

    # 2. Ollama stream rejects error frames and incomplete EOF streams without done=True
    class _FakeResp(io.BytesIO):
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    reasoner = OllamaReasoner(model="qwen2.5:1.5b")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_kw: _FakeResp(b'{"message":{"content":"partial"}}\n'),
    )
    with pytest.raises(LLMUnavailableError):
        reasoner._chat("sys", "hi", on_token=lambda _t: None)

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_kw: _FakeResp(b'{"error":"model killed"}\n'),
    )
    with pytest.raises(LLMUnavailableError):
        reasoner._chat("sys", "hi", on_token=lambda _t: None)

    # 3. Redacted PAN / sensitive strings must not leak into DB `course` metadata
    pan_doc = tmp_path / "notes.txt"
    pan_doc.write_text("Student PAN ABCDE1234F should stay encrypted and redacted.", encoding="utf-8")
    app = build_app(Settings(data_dir=tmp_path / "d", passphrase="pass", llm_backend="extractive"))
    res = ingest_file(pan_doc, app.db, app.vault)
    row = app.db.get_document(res.doc_id)
    assert row["sensitive"] == 1
    assert row["course"] is None

    # 4. Timetable guards missing start timestamps, renders Sunday when present, and escapes </script>
    import datetime as dt

    empty_fallback = build_timetable_report("23001", "Sem 7", [{"id": "old", "desc": "bad"}], current_class_ids={"cur"})
    assert empty_fallback.events == []
    sun_ts = int(dt.datetime(2026, 8, 9, 10, 0, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30))).timestamp())
    sun_report = build_timetable_report(
        "23001",
        "Sem 7",
        [{"id": "s1", "title": "CSE401C-07-A-L", "desc": "CSE401C : </script>AI", "start": sun_ts, "end": sun_ts + 3600}],
    )
    assert timetable_to_ui_props(sun_report)["calDayCount"] == 7
    html_out = format_timetable_html(sun_report)
    assert "\\u003c/script" in html_out and "\"SUN\"" in html_out

    # 5. Syllabus search strictly excludes mismatched degrees (BCA query drops MCA entry)
    bca_e = classify_syllabus_item({"text": "BCA Syllabus", "url": "https://www.dcrustm.ac.in/bca.pdf"})
    mca_e = classify_syllabus_item({"text": "MCA Syllabus", "url": "https://www.dcrustm.ac.in/mca.pdf"})
    syl_cat = SyllabusCatalog(source_url="https://cse.dcrust.online/syllabus", updated_at="now", entries=[bca_e, mca_e])
    syl_res = search_syllabus("BCA syllabus", tmp_path, catalog=syl_cat)
    assert [m.degree for m in syl_res.matches] == ["BCA"]

    # 6. PYQ partial sync preserves unselected sessions and blocks untrusted URLs
    class _PartialPyq(DcrustPyqClient):
        def fetch_catalog(self, *, exam_ids=None, max_workers=6, progress_cb=None):
            assert exam_ids == {"15"}
            return [{"exam_id": "15", "label": "dec2024"}], [
                PyqEntry("15", "December 2024", "2024-12_dec2024", 202412, "CSE302C", "CSE302C", "COMPILER", "dec24/CSE302C.pdf", "https://www.dcrustedp.in/dec24/CSE302C.pdf")
            ]

    pyq_dir = tmp_path / "pyqs"
    save_pyq_catalog(
        pyq_dir,
        PyqCatalog(
            source_url="https://www.dcrustedp.in/dcrustpqp.php",
            updated_at="old",
            exam_sessions=[{"exam_id": "14", "label": "june2024"}, {"exam_id": "15", "label": "dec2024"}],
            entries=[
                PyqEntry("14", "June 2024", "2024-06_june2024", 202406, "CSE301C", "CSE301C", "OS", "jun24/CSE301C.pdf", "https://www.dcrustedp.in/jun24/CSE301C.pdf")
            ],
        ),
    )
    merged = sync_dcrust_pyqs(pyq_dir, download=False, exam_ids={"15"}, client=_PartialPyq())
    assert {e.exam_id for e in merged.entries} == {"14", "15"}
    status_bad, sz_bad = DcrustPyqClient().download_pdf("https://evil.example.com/x.pdf", tmp_path / "bad.pdf")
    assert (status_bad, sz_bad) == ("invalid", 0)
    assert parse_exam_sessions("<a href='dcrustpqp2.php?examid=15'>dec2024</a>")[0][0] == "15"
