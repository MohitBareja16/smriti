"""Command-line interface: `parag ingest | ask | docs | facts | audit | demo | eval`."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from parag.app import build_app
from parag.config import Settings
from parag.ingest.parsers import SUPPORTED, UnsupportedFileError
from parag.llm import LLMUnavailableError
from parag.vault import VaultLockedError

DEFAULT_EVAL_DATA = Path("evals/data")


def _files(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in map(Path, paths):
        out += sorted(f for f in p.rglob("*") if f.suffix.lower() in SUPPORTED) if p.is_dir() else [p]
    return out


def cmd_ingest(args: argparse.Namespace) -> int:
    from parag.ingest import ingest_file

    app = build_app()
    for f in _files(args.paths):
        try:
            r = ingest_file(f, app.db, app.vault, course=args.course, kind=args.kind)
        except (UnsupportedFileError, VaultLockedError) as exc:
            print(f"✗ {f}: {exc}")
            continue
        state = "already ingested" if r.duplicate else (
            f"{r.doc_type}, {r.kind}{', sensitive (encrypted)' if r.sensitive else ''}, "
            f"{r.chunks} chunks, {r.facts} facts")
        print(f"✓ {r.title}: {state}")
    return 0


def print_answer(answer, show_trace: bool) -> None:
    badge = {"S1": "⚡ System 1 (fast)", "S2": "🧠 System 2 (agent)", "BLOCKED": "🛡 blocked",
             "PLAIN": "plain RAG"}[answer.path]
    print(f"\n{answer.text}\n")
    if answer.citations:
        print("Sources: " + "; ".join(answer.citations))
    print(f"[{badge} · intent={answer.intent} · confidence={answer.confidence:.2f} · "
          f"LLM calls={answer.llm_calls} · {answer.latency_ms:.0f} ms]")
    if show_trace:
        print("\nTrace:")
        for step in answer.trace:
            print(f"  {step.name:<20} {step.ms:7.1f} ms  {step.detail}")


def cmd_ask(args: argparse.Namespace) -> int:
    app = build_app()
    try:
        answer = app.orchestrator.handle(" ".join(args.question), mode=args.mode,
                                         guardrails=not args.no_guardrails)
    except LLMUnavailableError as exc:
        print(f"✗ {exc}")
        return 1
    print_answer(answer, args.trace)
    return 0


def cmd_docs(_: argparse.Namespace) -> int:
    for d in build_app().db.list_documents():
        lock = "🔒" if d["sensitive"] else "  "
        print(f"{d['id']:>3} {lock} {d['title']:<32} {d['doc_type']:<12} {d['kind']:<9} {d['course'] or ''}")
    return 0


def cmd_facts(_: argparse.Namespace) -> int:
    for f in build_app().db.all_facts():
        print(f"{f.attribute:<36} {f.value:<40} ({f.doc_title} p.{f.page})")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    import datetime as dt

    for row in build_app().db.audit_log(args.limit):
        ts = dt.datetime.fromtimestamp(row["ts"], tz=dt.timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{ts}  {row['action']:<8} {row['detail']}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from parag.demo import load_manifest

    if not os.environ.get("PARAG_PASSPHRASE"):
        os.environ["PARAG_PASSPHRASE"] = "demo"
        print("Using the demo vault passphrase 'demo' (export PARAG_PASSPHRASE=demo to fetch files later).")
    app = build_app()
    for r in load_manifest(Path(args.data) / "alex_demo", app):
        print(f"✓ {r.title}: {r.doc_type}, {r.kind}{' (encrypted)' if r.sensitive else ''}"
              f"{' (already loaded)' if r.duplicate else ''}")
    print('\nTry: parag ask "When is my DBMS exam?" --trace')
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from parag.evaluation import run_eval, to_markdown

    try:
        results = run_eval(Path(args.data), Settings(), systems=args.systems, out_dir=Path(args.out))
    except LLMUnavailableError as exc:
        print(f"✗ {exc}")
        return 1
    print(to_markdown(results))
    print(f"Saved to {args.out}/ (summary.md, summary.json, details.jsonl)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="parag", description="Personal Agentic RAG (System 1 + System 2)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="add files or folders")
    p.add_argument("paths", nargs="+")
    p.add_argument("--course", help="course name, e.g. OS")
    p.add_argument("--kind", choices=["library", "personal"], help="override auto-detection")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("ask", help="ask a question")
    p.add_argument("question", nargs="+")
    p.add_argument("--mode", choices=["ours", "agent", "plain"], default="ours")
    p.add_argument("--no-guardrails", action="store_true")
    p.add_argument("--trace", action="store_true", help="show every System 1 / System 2 step")
    p.set_defaults(func=cmd_ask)

    sub.add_parser("docs", help="list documents").set_defaults(func=cmd_docs)
    sub.add_parser("facts", help="list extracted facts").set_defaults(func=cmd_facts)

    p = sub.add_parser("audit", help="show the audit log")
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("demo", help="load the fictional Alex Demo student")
    p.add_argument("--data", default=str(DEFAULT_EVAL_DATA))
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("eval", help="run the evaluation (baselines vs ours)")
    p.add_argument("--data", default=str(DEFAULT_EVAL_DATA))
    p.add_argument("--out", default="evals/results")
    p.add_argument("--systems", nargs="*", help="subset of: plain_rag s2_only s1_s2_ours ours_no_guards")
    p.set_defaults(func=cmd_eval)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
