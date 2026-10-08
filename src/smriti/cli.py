"""Command-line interface.

    smriti ui --demo              open the chat UI with the fictional demo student
    smriti ui                     open the chat UI with your own documents
    smriti add <files/folders>    add your documents
    smriti ask "question"         ask from the terminal
    smriti docs | facts | audit   inspect what Smriti knows and did
    smriti traces | trace <id>    past answers and every step behind them
    smriti eval                   run the evaluation
    smriti experiment list|run    reproducible research experiments (see docs/research/)
"""

from __future__ import annotations

import argparse
import getpass
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from smriti.config import DEMO_DIR, DEMO_PASSPHRASE, Settings
from smriti.ingest.parsers import SUPPORTED, UnsupportedFileError
from smriti.llm import LLMUnavailableError, ollama_status
from smriti.vault import VaultLockedError

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DATA = REPO_ROOT / "evals" / "data"
UI_DIR = Path(__file__).resolve().parent / "ui"


# ---- helpers -------------------------------------------------------------------------------
def _use_demo() -> None:
    """Point Smriti at the demo folder, loading the fictional student the first time."""
    os.environ["SMRITI_DATA_DIR"] = str(DEMO_DIR)
    os.environ["SMRITI_PASSPHRASE"] = DEMO_PASSPHRASE
    from smriti.app import build_app
    from smriti.demo import load_manifest

    app = build_app()
    if not app.db.list_documents():
        print(f"Loading the demo student 'Alex Demo' (fictional data) into {DEMO_DIR} ...")
        for r in load_manifest(EVAL_DATA / "alex_demo", app):
            print(f"  ✓ {r.title} ({r.doc_type}{', encrypted' if r.sensitive else ''})")


def _ask_passphrase() -> None:
    """Ask once for the vault passphrase if it isn't set (needed to store or open personal files)."""
    if os.environ.get("SMRITI_PASSPHRASE") or not sys.stdin.isatty():
        return
    pw = getpass.getpass("Vault passphrase (protects your personal documents; Enter to skip): ")
    if pw:
        os.environ["SMRITI_PASSPHRASE"] = pw
    else:
        print("No passphrase: you can still use notes and books, but personal documents stay locked.")


def _choose_llm(quiet: bool = False) -> None:
    """Use the local Ollama model if it is ready, otherwise fall back to offline mode with a clear note."""
    s = Settings()
    if s.llm_backend != "ollama":
        return
    ok, msg = ollama_status(s.llm_model, s.ollama_url)
    if ok:
        if not quiet:
            print(f"🧠 {msg}")
        return
    os.environ["SMRITI_LLM"] = "extractive"
    print(f"⚠️  {msg}\n   Using offline mode: answers quote your documents directly instead of using an LLM.")


def _files(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in map(Path, paths):
        out += sorted(f for f in p.rglob("*") if f.suffix.lower() in SUPPORTED) if p.is_dir() else [p]
    return out


def _app(args: argparse.Namespace):
    if getattr(args, "demo", False):
        _use_demo()
    from smriti.app import build_app

    return build_app()


# ---- commands ------------------------------------------------------------------------------
def cmd_ui(args: argparse.Namespace) -> int:
    if importlib.util.find_spec("chainlit") is None:
        print("The chat UI isn't installed. Run:  pip install -e \".[ui]\"")
        return 1
    if args.demo:
        _use_demo()
    else:
        _ask_passphrase()
    _choose_llm()
    env = dict(os.environ, CHAINLIT_APP_ROOT=str(UI_DIR))
    cmd = [sys.executable, "-m", "chainlit", "run", str(UI_DIR / "chainlit_app.py"), "--port", str(args.port)]
    if args.no_browser:
        cmd.append("--headless")
    where = "the demo student" if args.demo else f"your documents in {Settings().data_dir}"
    print(f"\n✨ Smriti is starting with {where}.\n   Open http://localhost:{args.port} "
          "if your browser doesn't open by itself. Press Ctrl+C to stop.\n")
    sys.stdout.flush()
    try:
        return subprocess.call(cmd, env=env)
    except KeyboardInterrupt:
        return 0


def cmd_add(args: argparse.Namespace) -> int:
    from smriti.app import build_app
    from smriti.ingest import ingest_file

    _ask_passphrase()
    app = build_app()
    for f in _files(args.paths):
        try:
            r = ingest_file(f, app.db, app.vault, course=args.course, kind=args.kind)
        except (UnsupportedFileError, VaultLockedError, FileNotFoundError) as exc:
            print(f"✗ {f}: {exc}")
            continue
        state = "already added" if r.duplicate else (
            f"{r.doc_type}, {r.kind}{', encrypted' if r.sensitive else ''}, {r.chunks} chunks, {r.facts} facts")
        print(f"✓ {r.title}: {state}")
    print(f"\nStored in {app.settings.data_dir}. Next: smriti ui")
    return 0


def print_answer(answer, show_trace: bool) -> None:
    badge = {"S1": "⚡ System 1 (fast)", "S2": "🧠 System 2 (agent)", "BLOCKED": "🛡 blocked",
             "PLAIN": "plain RAG"}[answer.path]
    print(f"\n{answer.text}\n")
    if answer.citations:
        print("Sources: " + "; ".join(answer.citations))
    print(f"[{badge} · intent={answer.intent} · confidence={answer.confidence:.2f} · "
          f"LLM calls={answer.llm_calls} · {answer.latency_ms:.0f} ms · trace {answer.trace_id[:12]}]")
    if show_trace:
        print("\nTrace:")
        for step in answer.trace:
            print(f"  {step.name:<20} {step.ms:7.1f} ms  {step.detail}")


def cmd_ask(args: argparse.Namespace) -> int:
    if args.demo:
        _use_demo()
    _choose_llm(quiet=True)
    app = _app(argparse.Namespace())
    try:
        answer = app.orchestrator.handle(" ".join(args.question), mode=args.mode,
                                         guardrails=not args.no_guardrails)
    except LLMUnavailableError as exc:
        print(f"✗ {exc}")
        return 1
    print_answer(answer, args.trace)
    return 0


def cmd_docs(args: argparse.Namespace) -> int:
    for d in _app(args).db.list_documents():
        lock = "🔒" if d["sensitive"] else "  "
        print(f"{d['id']:>3} {lock} {d['title']:<32} {d['doc_type']:<12} {d['kind']:<9} {d['course'] or ''}")
    return 0


def cmd_facts(args: argparse.Namespace) -> int:
    for f in _app(args).db.all_facts():
        print(f"{f.attribute:<36} {f.value:<40} ({f.doc_title} p.{f.page})")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    import datetime as dt

    for row in _app(args).db.audit_log(args.limit):
        ts = dt.datetime.fromtimestamp(row["ts"], tz=dt.timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{ts}  {row['action']:<8} {row['detail']}")
    return 0


def cmd_traces(args: argparse.Namespace) -> int:
    import datetime as dt

    rows = _app(args).db.recent_traces(args.limit)
    if not rows:
        print("No traces yet. Ask something first: smriti ask \"...\"")
    for r in rows:
        ts = dt.datetime.fromtimestamp(r["ts"], tz=dt.timezone.utc).astimezone().strftime("%m-%d %H:%M")
        print(f"{r['trace_id'][:12]}  {ts}  {r['path']:<7} {r['intent']:<11} {r['latency_ms']:>8.0f} ms  "
              f"{r['question'][:60]}")
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    import json

    r = _app(args).db.get_trace(args.trace_id)
    if r is None:
        print(f"No single trace matches '{args.trace_id}'. See: smriti traces")
        return 1
    print(f"Trace {r['trace_id']}\nQuestion: {r['question']}\nPath: {r['path']} · intent {r['intent']} · "
          f"confidence {r['confidence']:.2f} · {r['latency_ms']:.0f} ms · LLM calls {r['llm_calls']} · "
          f"tokens {r['llm_tokens']}\n")
    for s in json.loads(r["steps"]):
        print(f"  {s['name']:<20} {s['ms']:8.1f} ms  {s['detail']}")
    return 0


def cmd_demo(_: argparse.Namespace) -> int:
    _use_demo()
    print('\nDemo ready. Next:\n  smriti ui --demo\n  smriti ask --demo "When is my DBMS exam?" --trace')
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from smriti.evaluation import run_eval, to_markdown

    _choose_llm()
    try:
        results = run_eval(Path(args.data), Settings(), systems=args.systems, out_dir=Path(args.out))
    except LLMUnavailableError as exc:
        print(f"✗ {exc}")
        return 1
    print(to_markdown(results))
    print(f"Saved to {args.out}/ (summary.md, summary.json, details.jsonl)")
    return 0


def cmd_experiment(args: argparse.Namespace) -> int:
    from smriti.research.experiments import load_config, run_experiment

    configs = sorted((REPO_ROOT / "experiments" / "configs").glob("*.json"))
    if args.action == "list":
        for c in configs:
            cfg = load_config(c)
            print(f"{c.name:<34} {cfg['type']:<20} {', '.join(cfg['research_questions']):<10} "
                  f"{cfg['settings'].get('llm_backend', 'ollama')}")
        return 0
    if not args.config:
        print("Give a config, e.g.:  smriti experiment run experiments/configs/tau_sweep_offline.json")
        return 1
    path = Path(args.config)
    if not path.exists():
        path = REPO_ROOT / "experiments" / "configs" / args.config
    cfg = load_config(path)
    if cfg["settings"].get("llm_backend", Settings().llm_backend) == "ollama":
        s = Settings()
        ok, msg = ollama_status(cfg["settings"].get("llm_model", s.llm_model), s.ollama_url)
        if not ok:
            print(f"✗ {msg}\n  This experiment needs the local model. Use an *_offline.json config instead.")
            return 1
    print(f"Running '{cfg['name']}' ({cfg['type']}, {', '.join(cfg['research_questions'])}) ...")
    try:
        run_dir = run_experiment(path)
    except LLMUnavailableError as exc:
        print(f"✗ {exc}")
        return 1
    print((run_dir / "summary.md").read_text())
    print(f"Saved to {run_dir.relative_to(REPO_ROOT) if run_dir.is_relative_to(REPO_ROOT) else run_dir}/")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smriti", description="Smriti: a private AI memory for your notes, books and documents.",
        epilog="New here? Run:  smriti ui --demo")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")
    demo_flag = argparse.ArgumentParser(add_help=False)
    demo_flag.add_argument("--demo", action="store_true", help="use the fictional demo student")

    p = sub.add_parser("ui", parents=[demo_flag], help="open the chat app in your browser")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    p.set_defaults(func=cmd_ui)

    p = sub.add_parser("add", aliases=["ingest"], help="add your files or folders")
    p.add_argument("paths", nargs="+")
    p.add_argument("--course", help="course name, e.g. OS")
    p.add_argument("--kind", choices=["library", "personal"],
                   help="library = notes/books, personal = marksheets/certificates (auto-detected)")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("ask", parents=[demo_flag], help="ask a question in the terminal")
    p.add_argument("question", nargs="+")
    p.add_argument("--trace", action="store_true", help="show every System 1 / System 2 step")
    p.add_argument("--mode", choices=["ours", "agent", "plain"], default="ours", help=argparse.SUPPRESS)
    p.add_argument("--no-guardrails", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_ask)

    sub.add_parser("docs", parents=[demo_flag], help="list your documents").set_defaults(func=cmd_docs)
    sub.add_parser("facts", parents=[demo_flag], help="list facts used for fast answers"
                   ).set_defaults(func=cmd_facts)
    p = sub.add_parser("audit", parents=[demo_flag], help="show what Smriti did (audit log)")
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("traces", parents=[demo_flag], help="list recent answers with their trace ids")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_traces)
    p = sub.add_parser("trace", parents=[demo_flag], help="show every step of one answer")
    p.add_argument("trace_id", help="trace id (or its first characters)")
    p.set_defaults(func=cmd_trace)

    sub.add_parser("demo", help="load the fictional demo student").set_defaults(func=cmd_demo)

    p = sub.add_parser("experiment", help="run a reproducible research experiment")
    p.add_argument("action", choices=["list", "run"])
    p.add_argument("config", nargs="?", help="path or file name in experiments/configs/")
    p.set_defaults(func=cmd_experiment)

    p = sub.add_parser("eval", help="run the evaluation (baselines vs Smriti)")
    p.add_argument("--data", default=str(EVAL_DATA))
    p.add_argument("--out", default="evals/results")
    p.add_argument("--systems", nargs="*", help="subset of: plain_rag s2_only s1_s2_ours ours_no_guards")
    p.set_defaults(func=cmd_eval)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
