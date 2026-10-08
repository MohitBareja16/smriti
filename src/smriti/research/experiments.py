"""Reproducible experiments.

An experiment is a JSON config in `experiments/configs/`. Running it writes a self-contained folder

    experiments/results/<UTC timestamp>_<name>/
        config.json        the exact config that ran
        environment.json   git commit, platform, model digest, settings (no secrets)
        dataset.json       SHA-256 fingerprint of the dataset files
        summary.json       headline metrics
        summary.md         the same, as a Markdown table for the report
        details.jsonl      one row per item, for error analysis
        *.csv / *.png      curves and plots (if the experiment produces them)

Config fields: name, type, research_questions, hypothesis, dataset, split, settings, params.
Supported types: see EXPERIMENTS below. Adding one = writing a function and registering it.
"""

from __future__ import annotations

import csv
import json
import time
from collections.abc import Callable
from dataclasses import asdict, fields
from pathlib import Path

from smriti.config import Settings
from smriti.evaluation import eval_app, run_eval, to_markdown
from smriti.research.datasets import fingerprint, load_split
from smriti.research.environment import REPO_ROOT, capture
from smriti.research.metrics import calibration, score_answer

REQUIRED = ("name", "type", "research_questions", "hypothesis")


def load_config(path: Path) -> dict:
    cfg = json.loads(Path(path).read_text())
    missing = [k for k in REQUIRED if k not in cfg]
    if missing:
        raise ValueError(f"{path}: missing required field(s): {', '.join(missing)}")
    if cfg["type"] not in EXPERIMENTS:
        raise ValueError(f"{path}: unknown type '{cfg['type']}'. Known: {', '.join(EXPERIMENTS)}")
    cfg.setdefault("dataset", "evals/data")
    cfg.setdefault("split", "dev")
    cfg.setdefault("settings", {})
    cfg.setdefault("params", {})
    return cfg


def make_settings(overrides: dict) -> Settings:
    s = Settings()
    known = {f.name for f in fields(Settings)}
    for k, v in overrides.items():
        if k not in known:
            raise ValueError(f"unknown setting '{k}'. Known: {', '.join(sorted(known))}")
        setattr(s, k, v)
    return s


# ---- experiment types ----------------------------------------------------------------------
def exp_baselines(cfg: dict, data_dir: Path, settings: Settings) -> dict:
    """RQ3/RQ4: plain RAG vs System 2 only vs System 1 + System 2, with a no-guardrails ablation."""
    results = run_eval(data_dir, settings, systems=cfg["params"].get("systems"), split=cfg["split"])
    summary = [{k: v for k, v in asdict(r).items() if k != "rows"} for r in results]
    return {"summary": summary, "markdown": to_markdown(results),
            "details": [row for r in results for row in r.rows]}


def exp_tau_sweep(cfg: dict, data_dir: Path, settings: Settings) -> dict:
    """RQ1/RQ2: how accuracy, System-1 share, latency and LLM cost change with the threshold tau.

    Exact and cheap: per question we compute (a) System 1's candidate answer and confidence and
    (b) the System 2 answer once. At threshold tau, Smriti answers with (a) iff confidence >= tau,
    otherwise with (b). So one pass covers every tau.
    """
    taus = cfg["params"].get("taus") or [round(0.05 * i, 2) for i in range(10, 21)]
    qa = load_split(data_dir / "qa.jsonl", cfg["split"])
    per_item = []
    with eval_app(data_dir, settings) as app:
        orch = app.orchestrator
        for item in qa:
            t0 = time.perf_counter()
            cand = orch.system1_candidate(item["question"])
            s1_ms = (time.perf_counter() - t0) * 1000
            s2 = orch.handle(item["question"], mode="agent")
            per_item.append({
                "id": item["id"], "intent": item["intent"],
                "s1_confidence": round(cand.confidence, 4) if cand else None,
                "s1_correct": score_answer(cand, item)["correct"] if cand else None,
                "s1_latency_ms": round(s1_ms, 2),
                "s2_correct": score_answer(s2, item)["correct"],
                "s2_latency_ms": round(s2.latency_ms, 1), "s2_llm_calls": s2.llm_calls,
                "s2_llm_tokens": s2.llm_tokens, "s2_answer": s2.text[:300],
                "s1_answer": cand.text[:300] if cand else None,
            })

    curve = []
    n = max(len(per_item), 1)
    for tau in taus:
        use_s1 = [r["s1_confidence"] is not None and r["s1_confidence"] >= tau for r in per_item]
        correct = [r["s1_correct"] if s else r["s2_correct"] for r, s in zip(per_item, use_s1)]
        latency = [r["s1_latency_ms"] if s else r["s1_latency_ms"] + r["s2_latency_ms"]
                   for r, s in zip(per_item, use_s1)]
        calls = [0 if s else r["s2_llm_calls"] for r, s in zip(per_item, use_s1)]
        tokens = [0 if s else r["s2_llm_tokens"] for r, s in zip(per_item, use_s1)]
        s1_answered = [c for c, s in zip(correct, use_s1) if s]
        curve.append({
            "tau": tau, "accuracy": round(sum(correct) / n, 4), "s1_share": round(sum(use_s1) / n, 4),
            "s1_precision": round(sum(s1_answered) / len(s1_answered), 4) if s1_answered else None,
            "mean_latency_ms": round(sum(latency) / n, 2), "llm_calls_per_q": round(sum(calls) / n, 3),
            "llm_tokens_per_q": round(sum(tokens) / n, 1),
        })
    always_s2 = {"accuracy": round(sum(r["s2_correct"] for r in per_item) / n, 4),
                 "mean_latency_ms": round(sum(r["s2_latency_ms"] for r in per_item) / n, 2)}

    md = ["| τ | Accuracy | S1 share | S1 precision | Mean latency (ms) | LLM calls/q | Tokens/q |",
          "|---|---|---|---|---|---|---|"]
    for c in curve:
        prec = f"{c['s1_precision']:.0%}" if c["s1_precision"] is not None else "–"
        md.append(f"| {c['tau']:.2f} | {c['accuracy']:.0%} | {c['s1_share']:.0%} | {prec} | "
                  f"{c['mean_latency_ms']:.0f} | {c['llm_calls_per_q']:.2f} | {c['llm_tokens_per_q']:.0f} |")
    md.append(f"\nReference, System 2 on every question: accuracy {always_s2['accuracy']:.0%}, "
              f"mean latency {always_s2['mean_latency_ms']:.0f} ms.")
    return {"summary": {"curve": curve, "always_system2": always_s2}, "markdown": "\n".join(md) + "\n",
            "details": per_item, "csv": {"tau_curve.csv": curve},
            "plot": ("tau_curve.png", _plot_tau, curve)}


def exp_router_calibration(cfg: dict, data_dir: Path, settings: Settings) -> dict:
    """Is the System-1 router's confidence trustworthy? Accuracy, ECE and a reliability table."""
    from smriti.decision import get_engine

    engine = get_engine(settings.s1_engine)
    rows = load_split(data_dir / "qa.jsonl", cfg["split"])
    extra = cfg["params"].get("router_file")
    if extra and (data_dir / extra).exists():
        rows += load_split(data_dir / extra, cfg["split"])
    details, conf, ok = [], [], []
    for item in rows:
        t0 = time.perf_counter()
        d = engine.route(item["question"])
        details.append({"id": item.get("id"), "question": item["question"], "gold": item["intent"],
                        "predicted": d.label, "confidence": round(d.probability, 4),
                        "correct": d.label == item["intent"], "ms": round((time.perf_counter() - t0) * 1000, 3)})
        conf.append(d.probability)
        ok.append(d.label == item["intent"])
    ece, bins = calibration(conf, ok, cfg["params"].get("bins", 10))
    acc = sum(ok) / max(len(ok), 1)
    md = [f"Engine `{engine.name}` on {len(rows)} questions: accuracy **{acc:.0%}**, ECE **{ece:.3f}**.\n",
          "| Confidence bin | Count | Mean confidence | Accuracy |", "|---|---|---|---|"]
    md += [f"| {b.lower:.1f}–{b.upper:.1f} | {b.count} | {b.mean_confidence:.2f} | {b.accuracy:.0%} |"
           for b in bins if b.count]
    return {"summary": {"engine": engine.name, "n": len(rows), "accuracy": round(acc, 4), "ece": round(ece, 4),
                        "bins": [asdict(b) for b in bins]},
            "markdown": "\n".join(md) + "\n", "details": details,
            "plot": ("reliability.png", _plot_reliability, bins)}


def exp_grounding_benchmark(cfg: dict, data_dir: Path, settings: Settings) -> dict:
    """RQ4/RQ3 (#9): which grounding check best separates supported from unsupported answer sentences?

    Computes every signal once per labelled (claim, evidence document) pair, then scores each rule
    over a threshold grid. False rejection = supported sentence rejected (causes over-abstention);
    catch rate = unsupported sentence rejected (stops hallucinations).
    """
    from smriti.decision import grounding as g
    from smriti.ingest.chunker import chunk_pages
    from smriti.ingest.parsers import parse

    items = load_split(data_dir / cfg["params"].get("file", "grounding.jsonl"), cfg["split"])
    docs: dict[str, list[str]] = {}
    rows = []
    t0 = time.perf_counter()
    for it in items:
        if it["evidence_doc"] not in docs:
            docs[it["evidence_doc"]] = [c for _, c in chunk_pages(parse(data_dir / "alex_demo" / it["evidence_doc"]))]
        ev = docs[it["evidence_doc"]]
        nli = g.nli_signals([it["claim"]], ev)[0]
        rows.append({"id": it["id"], "supported": it["supported"], "kind": it["kind"], "origin": it["origin"],
                     "lexical": round(g.lexical_coverage(it["claim"], ev), 4),
                     "entail": round(nli["entail"], 4), "contradict": round(nli["contradict"], 4),
                     "embedding": round(g.embedding_similarity([it["claim"]], ev)[0], 4), "claim": it["claim"]})
    ms_per_item = (time.perf_counter() - t0) * 1000 / max(len(items), 1)

    grid = cfg["params"].get("grid", {
        "lexical": [0.4, 0.5, 0.6, 0.7], "nli": [0.1, 0.3, 0.5, 0.7],
        "embedding": [0.5, 0.6, 0.7, 0.8], "hybrid": [0.5, 0.6, 0.7], "combined": [0.6, 0.7, 0.75, 0.8]})
    pos = [r for r in rows if r["supported"]]
    neg = [r for r in rows if not r["supported"]]
    table = []
    for rule, values in grid.items():
        for v in values:
            grounder = g.Grounder(rule=rule, thresholds={rule: v})
            ok = {r["id"]: grounder.decide(r).label == "yes" for r in rows}
            false_rej = sum(not ok[r["id"]] for r in pos) / max(len(pos), 1)
            catch = sum(not ok[r["id"]] for r in neg) / max(len(neg), 1)
            table.append({"rule": rule, "threshold": v, "false_rejection": round(false_rej, 4),
                          "catch_rate": round(catch, 4), "balanced_accuracy": round((1 - false_rej + catch) / 2, 4)})
    best = max(table, key=lambda r: (r["balanced_accuracy"], -r["false_rejection"]))
    current = next(r for r in table if r["rule"] == "lexical" and r["threshold"] == 0.6)

    md = [f"{len(pos)} supported and {len(neg)} unsupported sentences · signal time {ms_per_item:.0f} ms/sentence\n",
          "| Rule | Threshold | False rejection ↓ | Catch rate ↑ | Balanced accuracy ↑ |", "|---|---|---|---|---|"]
    for r in table:
        mark = " **(current)**" if r is current else (" **(best)**" if r is best else "")
        md.append(f"| {r['rule']}{mark} | {r['threshold']} | {r['false_rejection']:.0%} | {r['catch_rate']:.0%} | "
                  f"{r['balanced_accuracy']:.0%} |")
    return {"summary": {"n_supported": len(pos), "n_unsupported": len(neg), "ms_per_sentence": round(ms_per_item, 1),
                        "current": current, "best": best, "table": table},
            "markdown": "\n".join(md) + "\n", "details": rows, "csv": {"grounding_table.csv": table}}


EXPERIMENTS: dict[str, Callable[[dict, Path, Settings], dict]] = {
    "baselines": exp_baselines,
    "tau_sweep": exp_tau_sweep,
    "router_calibration": exp_router_calibration,
    "grounding_benchmark": exp_grounding_benchmark,
}


# ---- plots (optional: pip install -e ".[research]") ----------------------------------------
def _plt():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        return None


def _plot_tau(curve: list[dict], path: Path) -> bool:
    plt = _plt()
    if plt is None:
        return False
    fig, ax1 = plt.subplots(figsize=(7, 4.2))
    taus = [c["tau"] for c in curve]
    ax1.plot(taus, [c["accuracy"] for c in curve], marker="o", color="#2F6FB0", label="Accuracy")
    ax1.plot(taus, [c["s1_share"] for c in curve], marker="s", color="#E9A23B", label="Answered by System 1")
    ax1.set_xlabel("Confidence threshold τ")
    ax1.set_ylabel("Share of questions")
    ax1.set_ylim(0, 1.05)
    ax2 = ax1.twinx()
    ax2.plot(taus, [c["llm_calls_per_q"] for c in curve], linestyle="--", color="#6B7682", label="LLM calls / q")
    ax2.set_ylabel("LLM calls per question")
    ax2.set_ylim(0, max(1.0, 1.2 * max(c["llm_calls_per_q"] for c in curve)))
    lines = ax1.get_lines() + ax2.get_lines()
    ax1.legend(lines, [ln.get_label() for ln in lines], loc="lower left", frameon=False)
    ax1.set_title("Escalation curve: System 1 → System 2")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return True


def _plot_reliability(bins, path: Path) -> bool:
    plt = _plt()
    if plt is None:
        return False
    fig, ax = plt.subplots(figsize=(4.6, 4.4))
    used = [b for b in bins if b.count]
    ax.plot([0, 1], [0, 1], linestyle="--", color="#9AA8B5", label="Perfect calibration")
    ax.bar([(b.lower + b.upper) / 2 for b in used], [b.accuracy for b in used], width=0.09,
           color="#2F6FB0", alpha=0.85, label="Router accuracy")
    ax.set_xlabel("Router confidence")
    ax.set_ylabel("Accuracy")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False, loc="upper left")
    ax.set_title("Reliability diagram")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return True


# ---- runner --------------------------------------------------------------------------------
def run_experiment(config_path: Path, results_root: Path | None = None) -> Path:
    cfg = load_config(config_path)
    data_dir = (REPO_ROOT / cfg["dataset"]) if not Path(cfg["dataset"]).is_absolute() else Path(cfg["dataset"])
    settings = make_settings(cfg["settings"])
    env = capture(settings)  # before the run: the eval app replaces data_dir with a temp folder
    if settings.llm_backend == "ollama" and cfg["type"] != "model_matrix":
        # Same starting state for every run: model loaded, prompt cache empty. Without this, a run that
        # follows another on the same model reuses Ollama's prompt cache and looks faster (LOG 2026-10-09).
        from smriti.llm.ollama import unload, warm_up

        unload(settings.llm_model, settings.ollama_url)
        env["llm_cold_start_s"] = round(warm_up(settings.llm_model, settings.ollama_url), 2)
    started = time.perf_counter()
    out = EXPERIMENTS[cfg["type"]](cfg, data_dir, settings)
    env["duration_s"] = round(time.perf_counter() - started, 2)

    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    run_dir = (results_root or REPO_ROOT / "experiments" / "results") / f"{stamp}_{cfg['name']}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    (run_dir / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
    (run_dir / "dataset.json").write_text(json.dumps(fingerprint(data_dir), indent=2) + "\n")
    (run_dir / "summary.json").write_text(json.dumps(out["summary"], indent=2) + "\n")
    header = (f"# {cfg['name']}\n\n**Research questions:** {', '.join(cfg['research_questions'])}  \n"
              f"**Hypothesis:** {cfg['hypothesis']}  \n**Split:** {cfg['split']} · "
              f"**System 2:** {settings.llm_backend}"
              f"{' (' + settings.llm_model + ')' if settings.llm_backend == 'ollama' else ''} · "
              f"**System 1:** {settings.s1_engine} · **Commit:** `{(env['git_commit'] or '?')[:8]}`"
              f"{' (uncommitted changes)' if env['git_dirty'] else ''}\n\n")
    (run_dir / "summary.md").write_text(header + out["markdown"])
    (run_dir / "details.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out["details"]) + "\n")
    for name, rows in out.get("csv", {}).items():
        with open(run_dir / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    if "plot" in out:
        name, fn, data = out["plot"]
        fn(data, run_dir / name)
    return run_dir
