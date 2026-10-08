"""Tracing. Every step is recorded on the Answer (shown in CLI/UI) and, when enabled, exported as
OpenTelemetry spans to Arize Phoenix (`SMRITI_TRACING=phoenix`, needs the `tracing` extra).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from smriti.types import TraceStep

_otel_tracer = None


def setup_tracing(mode: str) -> bool:
    """Enable OpenTelemetry export. Returns True if tracing is active."""
    global _otel_tracer
    if mode != "phoenix":
        return False
    try:
        from opentelemetry import trace
        from phoenix.otel import register
    except ImportError:
        print("Tracing disabled: install with `pip install 'smriti[tracing]'` and run `phoenix serve`.")
        return False
    register(project_name="smriti")
    _otel_tracer = trace.get_tracer("smriti")
    return True


def set_otel_tracer(tracer) -> None:
    """Use a specific OpenTelemetry tracer (tests, or custom exporters). None disables export."""
    global _otel_tracer
    _otel_tracer = tracer


class Tracer:
    """Collects the steps of one request. Use `request()` once around the whole request so every
    step becomes a child of one root span (one trace per question in Phoenix)."""

    def __init__(self) -> None:
        self.steps: list[TraceStep] = []
        self.trace_id: str = uuid.uuid4().hex

    @contextmanager
    def request(self, name: str = "smriti.request", **attrs: Any) -> Iterator[dict[str, Any]]:
        """Root span. Yields a dict; keys set on it become attributes of the root span."""
        record: dict[str, Any] = {}
        if _otel_tracer is None:
            yield record
            return
        with _otel_tracer.start_as_current_span(name) as root:
            self.trace_id = format(root.get_span_context().trace_id, "032x")
            for k, v in attrs.items():
                root.set_attribute(f"smriti.{k}", str(v))
            yield record
            for k, v in record.items():
                root.set_attribute(f"smriti.{k}", str(v))

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[dict[str, Any]]:
        record: dict[str, Any] = {"detail": ""}
        start = time.perf_counter()
        if _otel_tracer is None:
            yield record
        else:
            with _otel_tracer.start_as_current_span(name) as otel_span:
                for k, v in attrs.items():
                    otel_span.set_attribute(f"smriti.{k}", str(v))
                yield record
                otel_span.set_attribute("smriti.detail", str(record["detail"]))
        self.steps.append(TraceStep(name, str(record["detail"]), (time.perf_counter() - start) * 1000))
