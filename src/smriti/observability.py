"""Tracing. Every step is recorded on the Answer (shown in CLI/UI) and, when enabled, exported as
OpenTelemetry spans to Arize Phoenix (`SMRITI_TRACING=phoenix`, needs the `tracing` extra).
"""

from __future__ import annotations

import time
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


class Tracer:
    """Collects the steps of one request."""

    def __init__(self) -> None:
        self.steps: list[TraceStep] = []

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
