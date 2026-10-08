import json

import pytest

from smriti import cli
from smriti.observability import set_otel_tracer


def test_every_answer_gets_a_unique_trace_id_and_is_stored(demo_app):
    a = demo_app.orchestrator.handle("When is my DBMS exam?")
    b = demo_app.orchestrator.handle("When is my DBMS exam?")
    assert len(a.trace_id) == 32 and a.trace_id != b.trace_id
    row = demo_app.db.get_trace(a.trace_id)
    assert row["path"] == "S1" and row["intent"] == "fact_lookup"
    steps = json.loads(row["steps"])
    assert [s["name"] for s in steps][:2] == ["s1.guard.input", "s1.router"]
    assert demo_app.db.get_trace(a.trace_id[:12])["trace_id"] == a.trace_id  # prefix lookup


def test_stored_traces_never_contain_raw_pii(demo_app):
    a = demo_app.orchestrator.handle("Is 9999 8888 7777 my Aadhaar? Mail me at x@example.com")
    row = demo_app.db.get_trace(a.trace_id)
    stored = row["question"] + row["steps"]
    assert "9999 8888 7777" not in stored and "x@example.com" not in stored
    assert "9999" not in demo_app.db.audit_log(1)[0]["detail"]


def test_all_spans_of_one_request_share_one_trace(demo_app):
    sdk = pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = sdk.TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    set_otel_tracer(provider.get_tracer("test"))
    try:
        a = demo_app.orchestrator.handle("Explain the four conditions for deadlock from my OS notes")
    finally:
        set_otel_tracer(None)
    spans = exporter.get_finished_spans()
    assert len(spans) > 3
    assert {format(s.context.trace_id, "032x") for s in spans} == {a.trace_id}
    roots = [s for s in spans if s.parent is None]
    assert [r.name for r in roots] == ["smriti.request"]
    assert roots[0].attributes["smriti.path"] == "S2"


def test_cli_traces_and_trace(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "DEMO_DIR", tmp_path / "demo")
    monkeypatch.setenv("SMRITI_LLM", "extractive")
    cli.main(["ask", "--demo", "When is my DBMS exam?"])
    out = capsys.readouterr().out
    tid = out.split("trace ")[-1].split("]")[0].strip()
    cli.main(["traces", "--demo"])
    assert tid in capsys.readouterr().out
    assert cli.main(["trace", "--demo", tid]) == 0
    assert "s1.facts_lookup" in capsys.readouterr().out
