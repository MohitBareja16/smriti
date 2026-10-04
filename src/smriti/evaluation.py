"""Evaluation harness: compares plain RAG, System 2 only, and System 1 + System 2 (ours), with and
without guardrails, on the public Alex Demo dataset. Produces the tables for RQ1 to RQ4.
"""

from __future__ import annotations

import json
import statistics
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from smriti.app import build_app
from smriti.config import Settings
from smriti.demo import load_manifest
from smriti.guardrails import IDK
from smriti.types import Answer

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
    attack_success_rate: float = 0.0
    leak_rate: float = 0.0
    false_refusal_rate: float = 0.0
    router_accuracy: float | None = None
    rows: list[dict] = field(default_factory=list)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _is_idk(a: Answer) -> bool:
    return a.text.strip() == IDK or "don't know" in a.text.lower()


def _p(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, round(q * (len(values) - 1)))]


def run_eval(data_dir: Path, settings: Settings | None = None, systems: list[str] | None = None,
             out_dir: Path | None = None) -> list[SystemResult]:
    qa = _read_jsonl(data_dir / "qa.jsonl")
    redteam = _read_jsonl(data_dir / "redteam.jsonl")
    results: list[SystemResult] = []

    with tempfile.TemporaryDirectory() as tmp:
        settings = settings or Settings()
        settings.data_dir = Path(tmp)
        settings.passphrase = settings.passphrase or "eval-only-passphrase"
        app = build_app(settings)
        load_manifest(data_dir / "alex_demo", app)
        orch = app.orchestrator

        for name in systems or list(SYSTEMS):
            cfg = SYSTEMS[name]
            r = SystemResult(system=name)
            latencies, calls, correct, cited, s1, idk_ok, idk_total, routed = [], [], 0, 0, 0, 0, 0, 0
            answerable = [q for q in qa if not q.get("expect_idk")]
            for item in qa:
                t0 = time.perf_counter()
                a = orch.handle(item["question"], mode=cfg["mode"], guardrails=cfg["guardrails"])
                latencies.append((time.perf_counter() - t0) * 1000)
                calls.append(a.llm_calls)
                s1 += a.path == "S1"
                routed += a.intent == item["intent"]
                if item.get("expect_idk"):
                    idk_total += 1
                    ok = _is_idk(a)
                    idk_ok += ok
                else:
                    haystack = f"{a.text} {' '.join(a.citations)} {a.attachment or ''}".lower()
                    ok = all(s.lower() in haystack for s in item["expect_contains"])
                    correct += ok
                    cited += any(item["expect_source"] in c for c in a.citations)
                r.rows.append({"system": name, "id": item["id"], "ok": ok, "path": a.path, "intent": a.intent,
                               "llm_calls": a.llm_calls, "answer": a.text[:200], "citations": a.citations})

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
                r.rows.append({"system": name, "id": item["id"], "path": a.path, "answer": a.text[:200]})

            r.accuracy = correct / len(answerable)
            r.citation_accuracy = cited / len(answerable)
            r.idk_accuracy = idk_ok / idk_total if idk_total else 0.0
            r.s1_share = s1 / len(qa)
            r.latency_p50_ms = statistics.median(latencies)
            r.latency_p95_ms = _p(latencies, 0.95)
            r.llm_calls_per_q = sum(calls) / len(calls)
            r.attack_success_rate = succeeded / len(attacks) if attacks else 0.0
            r.leak_rate = leaked / len(leaks) if leaks else 0.0
            r.false_refusal_rate = refused / len(benign) if benign else 0.0
            if cfg["mode"] != "plain":
                r.router_accuracy = routed / len(qa)
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
