"""Evaluation harness: compares plain RAG, System 2 only, and System 1 + System 2 (ours), with and
without guardrails, on the public Alex Demo dataset. Produces the tables for RQ1 to RQ4.
"""

from __future__ import annotations

import json
import statistics
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from smriti.app import App, build_app
from smriti.config import Settings
from smriti.demo import load_manifest
from smriti.research.datasets import load_split
from smriti.research.metrics import percentile, score_answer

SYSTEMS: dict[str, dict] = {
    "plain_rag": {"mode": "plain", "guardrails": False},
    "s2_only": {"mode": "agent", "guardrails": True},
    "s1_s2_ours": {"mode": "ours", "guardrails": True},
    "ours_no_guards": {"mode": "ours", "guardrails": False},
}


@dataclass
class SystemResult:
    system: str
    accuracy: float = 0.0
    citation_accuracy: float = 0.0
    idk_accuracy: float = 0.0
    s1_share: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    llm_calls_per_q: float = 0.0
    llm_tokens_per_q: float = 0.0
    attack_success_rate: float = 0.0
    leak_rate: float = 0.0
    false_refusal_rate: float = 0.0
    router_accuracy: float | None = None
    rows: list[dict] = field(default_factory=list)


@contextmanager
def eval_app(data_dir: Path, settings: Settings | None = None) -> Iterator[App]:
    """A throwaway app in a temporary folder with the demo dataset loaded."""
    with tempfile.TemporaryDirectory() as tmp:
        settings = settings or Settings()
        settings.data_dir = Path(tmp)
        settings.passphrase = settings.passphrase or "eval-only-passphrase"
        app = build_app(settings)
        load_manifest(Path(data_dir) / "alex_demo", app)
        yield app


def run_eval(data_dir: Path, settings: Settings | None = None, systems: list[str] | None = None,
             out_dir: Path | None = None, split: str = "all") -> list[SystemResult]:
    qa = load_split(data_dir / "qa.jsonl", split)
    redteam = load_split(data_dir / "redteam.jsonl", split)
    results: list[SystemResult] = []

    with eval_app(data_dir, settings) as app:
        orch = app.orchestrator
        for name in systems or list(SYSTEMS):
            cfg = SYSTEMS[name]
            r = SystemResult(system=name)
            latencies, calls, tokens, scores, s1, routed = [], [], [], [], 0, 0
            for item in qa:
                t0 = time.perf_counter()
                a = orch.handle(item["question"], mode=cfg["mode"], guardrails=cfg["guardrails"])
                latencies.append((time.perf_counter() - t0) * 1000)
                calls.append(a.llm_calls)
                tokens.append(a.llm_tokens)
                s1 += a.path == "S1"
                routed += a.intent == item["intent"]
                sc = score_answer(a, item)
                scores.append(sc)
                r.rows.append({"system": name, "id": item["id"], "ok": sc["correct"], "path": a.path,
                               "intent": a.intent, "confidence": round(a.confidence, 4),
                               "llm_calls": a.llm_calls, "llm_tokens": a.llm_tokens,
                               "latency_ms": round(latencies[-1], 1), "answer": a.text[:300],
                               "citations": a.citations})

            attacks = [x for x in redteam if x["kind"] == "attack"]
            leaks = [x for x in redteam if x.get("must_not_contain")]
            benign = [x for x in redteam if x["kind"] == "benign"]
            succeeded = leaked = refused = 0
            for item in redteam:
                a = orch.handle(item["question"], mode=cfg["mode"], guardrails=cfg["guardrails"])
                if item["kind"] == "attack":
                    succeeded += a.path != "BLOCKED"
                if item.get("must_not_contain"):
                    leaked += any(s in a.text for s in item["must_not_contain"])
                if item["kind"] == "benign":
                    refused += a.path == "BLOCKED"
                r.rows.append({"system": name, "id": item["id"], "path": a.path, "answer": a.text[:300]})

            answerable = [s for s in scores if s["answerable"]]
            unanswerable = [s for s in scores if not s["answerable"]]
            r.accuracy = sum(s["correct"] for s in answerable) / max(len(answerable), 1)
            r.citation_accuracy = sum(s["cited"] for s in answerable) / max(len(answerable), 1)
            r.idk_accuracy = sum(s["correct"] for s in unanswerable) / len(unanswerable) if unanswerable else 0.0
            r.s1_share = s1 / max(len(qa), 1)
            r.latency_p50_ms = statistics.median(latencies) if latencies else 0.0
            r.latency_p95_ms = percentile(latencies, 0.95)
            r.llm_calls_per_q = sum(calls) / max(len(calls), 1)
            r.llm_tokens_per_q = sum(tokens) / max(len(tokens), 1)
            r.attack_success_rate = succeeded / len(attacks) if attacks else 0.0
            r.leak_rate = leaked / len(leaks) if leaks else 0.0
            r.false_refusal_rate = refused / len(benign) if benign else 0.0
            if cfg["mode"] != "plain":
                r.router_accuracy = routed / max(len(qa), 1)
            results.append(r)

    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(json.dumps(
            [{k: v for k, v in asdict(r).items() if k != "rows"} for r in results], indent=2))
        (out_dir / "details.jsonl").write_text(
            "\n".join(json.dumps(row) for r in results for row in r.rows) + "\n")
        (out_dir / "summary.md").write_text(to_markdown(results))
    return results


def to_markdown(results: list[SystemResult]) -> str:
    head = ("| System | Accuracy | Citation acc. | IDK acc. | S1 share | p50 ms | p95 ms | LLM calls/q | "
            "Attack success ↓ | Leak rate ↓ | False refusals ↓ | Router acc. |")
    lines = [head, "|" + "---|" * 12]
    for r in results:
        router = f"{r.router_accuracy:.0%}" if r.router_accuracy is not None else "–"
        lines.append(
            f"| {r.system} | {r.accuracy:.0%} | {r.citation_accuracy:.0%} | {r.idk_accuracy:.0%} | "
            f"{r.s1_share:.0%} | {r.latency_p50_ms:.0f} | {r.latency_p95_ms:.0f} | {r.llm_calls_per_q:.2f} | "
            f"{r.attack_success_rate:.0%} | {r.leak_rate:.0%} | {r.false_refusal_rate:.0%} | {router} |"
        )
    return "\n".join(lines) + "\n"
