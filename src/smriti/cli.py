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
    from smriti.llm import list_ollama_models

    s = Settings()
    if s.llm_backend != "ollama":
        return
    # If user didn't force SMRITI_LLM_MODEL, prefer pulled 8 GB CPU-friendly models cleanly.
    if not os.environ.get("SMRITI_LLM_MODEL"):
        installed = list_ollama_models(s.ollama_url)
        if installed:
            preferred = [s.llm_model, "qwen2.5:1.5b", "qwen2.5:3b", "qwen2.5:0.5b"]
            for cand in preferred:
                if any(n == cand or n.split(":")[0] == cand or n == f"{cand}:latest" for n in installed):
                    if cand != s.llm_model:
                        os.environ["SMRITI_LLM_MODEL"] = cand
                        s = Settings()
                    break
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
    web_dist = UI_DIR / "web" / "dist"
    use_chainlit = getattr(args, "legacy_chainlit", False) or not (web_dist / "index.html").is_file()
    if not use_chainlit and importlib.util.find_spec("uvicorn") is not None and importlib.util.find_spec("fastapi") is not None:
        return cmd_serve(args)
    if importlib.util.find_spec("chainlit") is None:
        print("The chat UI isn't installed. Run:  pip install -e \".[ui,docx]\"")
        return 1
    if args.demo:
        _use_demo()
    else:
        _ask_passphrase()
    _choose_llm()
    env = dict(os.environ, CHAINLIT_APP_ROOT=str(UI_DIR))
    # Chainlit treats DEBUG as its boolean debug flag. Some environments set
    # DEBUG=release, which makes the CLI reject startup before loading the app.
    env.pop("DEBUG", None)
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


def cmd_serve(args: argparse.Namespace) -> int:
    if importlib.util.find_spec("uvicorn") is None or importlib.util.find_spec("fastapi") is None:
        print("FastAPI server dependencies aren't installed. Run:  pip install -e \".[ui,docx]\"")
        return 1
    import threading

    import uvicorn

    from smriti.desktop import open_browser_quietly

    if args.demo:
        _use_demo()
    else:
        _ask_passphrase()
    _choose_llm()
    from smriti.app import build_app
    from smriti.server import create_app

    host = getattr(args, "host", "127.0.0.1")
    no_browser = getattr(args, "no_browser", True)
    static_dist = UI_DIR / "web" / "dist"
    web_app = create_app(build_app(), static_dir=static_dist if (static_dist / "index.html").is_file() else None)
    url = f"http://{host}:{args.port}"
    where = "the demo student" if args.demo else f"your documents in {Settings().data_dir}"
    print(f"\n✨ Smriti is starting with {where}.\n   Open {url} in your browser. Press Ctrl+C to stop.\n")
    sys.stdout.flush()
    if not no_browser:
        threading.Timer(0.9, lambda: open_browser_quietly(url)).start()
    uvicorn.run(web_app, host=host, port=args.port, log_level="warning")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    from smriti.app import build_app
    from smriti.ingest import ingest_file

    _ask_passphrase()
    app = build_app()
    for f in _files(args.paths):
        try:
            r = ingest_file(f, app.db, app.vault, course=args.course, semester=args.semester, kind=args.kind)
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
        answer = app.orchestrator.handle(
            " ".join(args.question),
            mode=args.mode,
            guardrails=not args.no_guardrails,
            thread_id=getattr(args, "thread", None),
        )
    except LLMUnavailableError as exc:
        print(f"✗ {exc}")
        return 1
    print_answer(answer, args.trace)
    return 0


def cmd_attendance(args: argparse.Namespace) -> int:
    from smriti.app import build_app
    from smriti.university import (
        SamarthError,
        clear_samarth_credentials,
        format_attendance_html,
        format_attendance_markdown,
        load_samarth_credentials,
        parse_a10dance_html,
        save_samarth_credentials,
        sync_samarth_attendance,
    )

    _ask_passphrase()
    app = build_app()

    if args.clear:
        removed = clear_samarth_credentials(app.vault)
        print("✓ Cleared saved Samarth credentials." if removed else "No saved Samarth credentials found.")
        return 0

    if args.from_mht:
        raw = Path(args.from_mht).read_text(encoding="utf-8", errors="replace")
        report = parse_a10dance_html(raw, roll_number=args.roll or "snapshot")
        print("\n" + format_attendance_markdown(report))
        out_dir = app.settings.data_dir / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_html = out_dir / "dcrust_attendance_snapshot.html"
        out_html.write_text(format_attendance_html(report), encoding="utf-8")
        print(f"\nHTML dashboard saved to: {out_html}")
        return 0

    roll = args.roll
    pwd = None
    if not args.login:
        saved = load_samarth_credentials(app.vault)
        if saved:
            roll = roll or saved[0]
            pwd = saved[1]

    if not roll or not pwd or args.login:
        roll = roll or input("eSamarth Roll Number: ").strip()
        pwd = getpass.getpass("eSamarth Password: ")
        if args.login and not args.no_save and app.vault.unlocked:
            save_samarth_credentials(app.vault, roll, pwd)

    try:
        report, html_path = sync_samarth_attendance(
            app.db,
            app.vault,
            app.settings.data_dir,
            roll_number=roll,
            password=pwd,
            save_creds=not args.no_save,
        )
    except SamarthError as exc:
        print(f"✗ {exc}")
        return 1

    print("\n" + format_attendance_markdown(report))
    print(f"\n✓ Synced {len(report.subjects)} subjects into Smriti RAG & saved HTML card view to: {html_path}")
    return 0


def cmd_timetable(args: argparse.Namespace) -> int:
    from smriti.app import build_app
    from smriti.university import (
        SamarthError,
        format_timetable_markdown,
        load_samarth_credentials,
        save_samarth_credentials,
        sync_samarth_timetable,
    )

    _ask_passphrase()
    app = build_app()
    roll = args.roll
    pwd = None
    if not args.login:
        saved = load_samarth_credentials(app.vault)
        if saved:
            roll = roll or saved[0]
            pwd = saved[1]
    if not roll or not pwd or args.login:
        roll = roll or input("eSamarth Roll Number: ").strip()
        pwd = getpass.getpass("eSamarth Password: ")
        if args.login and not args.no_save and app.vault.unlocked:
            save_samarth_credentials(app.vault, roll, pwd)

    try:
        report, html_path = sync_samarth_timetable(
            app.db,
            app.vault,
            app.settings.data_dir,
            roll_number=roll,
            password=pwd,
            save_creds=not args.no_save,
        )
    except SamarthError as exc:
        print(f"✗ {exc}")
        return 1

    print("\n" + format_timetable_markdown(report))
    print(f"\n✓ Synced weekly table + calendar into Smriti RAG & saved HTML view to: {html_path}")
    return 0


def cmd_pyq(args: argparse.Namespace) -> int:
    from smriti.university.pyq import format_pyq_markdown, search_pyqs, sync_dcrust_pyqs

    target_dir = Path(args.dir).expanduser() if args.dir else Settings().pyq_dir
    if args.action == "sync":
        print(f"Syncing DCRUST PYQs from dcrustedp.in into {target_dir} ...")
        exam_ids = set(args.exam_id) if args.exam_id else None
        catalog = sync_dcrust_pyqs(
            target_dir,
            download=not args.index_only,
            max_workers=args.workers,
            exam_ids=exam_ids,
            progress_cb=lambda msg: print(f"  {msg}", flush=True),
        )
        downloaded = sum(1 for e in catalog.entries if e.status == "downloaded")
        missing = sum(1 for e in catalog.entries if e.status == "missing_remote")
        print(
            f"\n✓ Indexed {len(catalog.entries):,} papers across {len(catalog.exam_sessions)} exam sessions "
            f"({downloaded:,} downloaded, {missing:,} unavailable remotely)."
        )
        print(f"  Sorted by subject: {target_dir / 'by_subject'}")
        print(f"  Sorted by session: {target_dir / 'by_session'}")
        print(f"  Catalog index:     {target_dir / 'index.json'}")
        return 0

    query = " ".join(args.query or []).strip()
    if not query:
        print("Provide a subject code or name, e.g.:  smriti pyq search CSE302C")
        return 1
    result = search_pyqs(query, target_dir)
    print("\n" + format_pyq_markdown(result, target_dir))
    return 0


def cmd_syllabus(args: argparse.Namespace) -> int:
    from smriti.university.syllabus import format_syllabus_markdown, search_syllabus, sync_dcrust_syllabus

    target_dir = Path(args.dir).expanduser() if args.dir else Settings().syllabus_dir
    if args.action == "sync":
        print(f"Syncing DCRUST university syllabi into {target_dir} ...")
        catalog = sync_dcrust_syllabus(
            target_dir,
            download=not args.index_only,
            max_workers=args.workers,
            progress_cb=lambda msg: print(f"  {msg}", flush=True),
        )
        downloaded = sum(1 for e in catalog.entries if e.status == "downloaded")
        print(
            f"\n✓ Indexed {len(catalog.entries)} syllabus documents "
            f"({downloaded} downloaded locally)."
        )
        print(f"  Sorted by branch: {target_dir / 'by_branch'}")
        print(f"  Sorted by year:   {target_dir / 'by_year'}")
        print(f"  Catalog index:    {target_dir / 'index.json'}")
        return 0

    query = " ".join(args.query or []).strip()
    if not query:
        print("Provide branch/year, e.g.:  smriti syllabus search CSE 3rd year")
        return 1
    result = search_syllabus(query, target_dir)
    print("\n" + format_syllabus_markdown(result, target_dir))
    return 0


def cmd_docs(args: argparse.Namespace) -> int:
    for d in _app(args).db.list_documents():
        lock = "🔒" if d["sensitive"] else "  "
        print(f"{d['id']:>3} {lock} {d['title']:<32} {d['doc_type']:<12} {d['kind']:<9} {d['course'] or ''}")
    return 0


def cmd_library(args: argparse.Namespace) -> int:
    from smriti.library import build_tree, render_tree

    rows = _app(args).db.library_tree()
    print(render_tree(build_tree(rows), show_topics=not args.no_topics) if rows else
          "Your library is empty. Add notes with: smriti add <folder> --course OS --semester 5")
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    from smriti.graph import KnowledgeGraph

    g = KnowledgeGraph(_app(args).db)
    if args.rebuild or not g.counts():
        g.rebuild()
    if not args.entity:
        counts = g.counts()
        print("Knowledge graph: " + ", ".join(f"{n} {t.lower()}{'s' if n != 1 else ''}" for t, n in counts.items()))
        for type_ in ("Course", "Project", "Certification", "Skill"):
            if counts.get(type_):
                print(f"  {type_}s: {', '.join(g.names(type_))}")
        print('\nInspect one: smriti graph "DBMS"')
        return 0
    rows = g.neighbors(args.entity)
    if not rows:
        print(f"Nothing called '{args.entity}' in the graph. Try: smriti graph")
        return 1
    for direction, rel, other, ref in rows:
        arrow = f"–{rel}→" if direction == "out" else f"←{rel}–"
        print(f"  {args.entity} {arrow} {other}   ({ref})")
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


def cmd_demo(args: argparse.Namespace) -> int:
    if args.reset and DEMO_DIR.exists():
        import shutil

        shutil.rmtree(DEMO_DIR)
        print(f"Removed the old demo library at {DEMO_DIR}.")
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


def cmd_train_router(args: argparse.Namespace) -> int:
    from smriti.decision.learned import EmbeddingRouter, default_model_path, training_data

    questions, labels = training_data(Path(args.data))
    print(f"Training the embedding router on {len(questions)} labelled questions ({args.model}) ...")
    router = EmbeddingRouter(model=args.model).fit(questions, labels)
    path = router.save(default_model_path())
    print(f"✓ Saved to {path} (temperature {router.temperature}). Use it with: export SMRITI_S1_ENGINE=embedding")
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
    print((run_dir / "summary.md").read_text(encoding="utf-8"))
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
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    p.add_argument("--legacy-chainlit", action="store_true", help="use the legacy Chainlit UI instead of the React Web UI")
    p.set_defaults(func=cmd_ui)

    p = sub.add_parser("serve", aliases=["api"], parents=[demo_flag], help="run the FastAPI backend server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-browser", action="store_true", default=True, help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("add", aliases=["ingest"], help="add your files or folders")
    p.add_argument("paths", nargs="+")
    p.add_argument("--course", help="course name, e.g. OS")
    p.add_argument("--semester", type=int, help="semester number (auto-detected from paths like sem5/)")
    p.add_argument("--kind", choices=["library", "personal"],
                   help="library = notes/books, personal = marksheets/certificates (auto-detected)")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("ask", parents=[demo_flag], help="ask a question in the terminal")
    p.add_argument("question", nargs="+")
    p.add_argument("--thread", help="conversation thread id for multi-turn context window")
    p.add_argument("--trace", action="store_true", help="show every System 1 / System 2 step")
    p.add_argument("--mode", choices=["ours", "agent", "plain"], default="ours", help=argparse.SUPPRESS)
    p.add_argument("--no-guardrails", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_ask)

    sub.add_parser("docs", parents=[demo_flag], help="list your documents").set_defaults(func=cmd_docs)

    p = sub.add_parser("attendance", aliases=["samarth"], help="fetch live attendance from DCRUST eSamarth")
    p.add_argument("--roll", help="eSamarth roll number / enrolment number")
    p.add_argument("--login", action="store_true", help="enter and save encrypted eSamarth credentials")
    p.add_argument("--clear", action="store_true", help="remove saved eSamarth credentials from the vault")
    p.add_argument("--no-save", action="store_true", help="do not store eSamarth credentials in the vault")
    p.add_argument("--from-mht", help="parse and render a saved a10dance.com .mht/.html file")
    p.set_defaults(func=cmd_attendance)

    p = sub.add_parser("timetable", aliases=["calendar"], help="fetch current-semester weekly timetable & calendar from DCRUST eSamarth")
    p.add_argument("--roll", help="eSamarth roll number / enrolment number")
    p.add_argument("--login", action="store_true", help="enter and save encrypted eSamarth credentials")
    p.add_argument("--no-save", action="store_true", help="do not store eSamarth credentials in the vault")
    p.set_defaults(func=cmd_timetable)

    p = sub.add_parser("pyq", aliases=["pyqs"], help="download, sort, and search DCRUST PYQs from dcrustedp.in")
    p.add_argument("action", choices=["sync", "search"], help="'sync' downloads & sorts all PYQs; 'search' finds by code/name")
    p.add_argument("query", nargs="*", help="subject code or subject name (for 'search')")
    p.add_argument("--dir", help="target PYQ folder (defaults to ./pyqs or SMRITI_PYQ_DIR)")
    p.add_argument("--workers", type=int, default=12, help="concurrent download workers (default: 12)")
    p.add_argument("--exam-id", action="append", help="restrict sync to specific examid(s)")
    p.add_argument("--index-only", action="store_true", help="only build sorted catalog index without downloading PDFs")
    p.set_defaults(func=cmd_pyq)

    p = sub.add_parser("syllabus", aliases=["syllabi"], help="download, sort, and search DCRUST syllabi by branch and year")
    p.add_argument("action", choices=["sync", "search"], help="'sync' downloads & sorts all syllabi; 'search' finds by branch/year")
    p.add_argument("query", nargs="*", help="branch and year query, e.g. 'CSE 3rd year'")
    p.add_argument("--dir", help="target syllabus folder (defaults to ./syllabus or SMRITI_SYLLABUS_DIR)")
    p.add_argument("--workers", type=int, default=8, help="concurrent download workers (default: 8)")
    p.add_argument("--index-only", action="store_true", help="only build sorted catalog index without downloading files")
    p.set_defaults(func=cmd_syllabus)
    p = sub.add_parser("graph", parents=[demo_flag], help="knowledge graph: courses, skills, projects")
    p.add_argument("entity", nargs="?", help="show connections of one entity, e.g. DBMS")
    p.add_argument("--rebuild", action="store_true")
    p.set_defaults(func=cmd_graph)
    p = sub.add_parser("library", parents=[demo_flag], help="your library: semester → course → topics")
    p.add_argument("--no-topics", action="store_true")
    p.set_defaults(func=cmd_library)
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

    p = sub.add_parser("demo", help="load the fictional demo student")
    p.add_argument("--reset", action="store_true", help="delete and rebuild the demo library")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("train-router", help="train the learned System-1 router (needs the ml extra)")
    p.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2", help="sentence-transformers model")
    p.add_argument("--data", default=str(EVAL_DATA))
    p.set_defaults(func=cmd_train_router)

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
    # CLI help and status messages include arrows and symbols; use UTF-8 in Windows consoles.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
