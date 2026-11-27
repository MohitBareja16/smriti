"""Single-click Desktop / Windows launcher for bundled Smriti distributions."""

from __future__ import annotations

import argparse
import atexit
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from contextlib import contextmanager
from pathlib import Path


def bundle_root() -> Path:
    """Resolve root directory containing bundled assets (PyInstaller frozen vs editable checkout)."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "_internal").is_dir() and not (exe_dir / "pyqs").exists():
            # PyInstaller >= 6 puts _MEIPASS in _internal, user data folders live beside the .exe
            return exe_dir
        return exe_dir
    return Path(__file__).resolve().parents[2]


def internal_root() -> Path:
    """Resolve PyInstaller internal data directory (`sys._MEIPASS`) or package parent."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[1]


def open_browser_quietly(url: str) -> None:
    """Open URL in the default browser without forwarding Chromium/linker stderr to the console."""
    if sys.platform == "win32" and hasattr(os, "startfile"):
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return
        except OSError:
            pass
    opener = shutil.which("xdg-open") if sys.platform.startswith("linux") else shutil.which("open")
    if opener:
        try:
            subprocess.Popen(
                [opener, url],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
            return
        except OSError:
            pass
    webbrowser.open(url)


def default_data_dir(base: Path) -> Path:
    """Choose writable persistent data directory beside portable bundle or in LocalAppData."""
    portable_data = base / "data"
    if (base / ".portable").exists() or os.access(base, os.W_OK):
        portable_data.mkdir(parents=True, exist_ok=True)
        return portable_data
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        d = Path(local_app) / "Smriti" / "data"
    else:
        d = Path.home() / ".smriti" / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.35)
        return sock.connect_ex((host, port)) == 0


def pick_port(host: str = "127.0.0.1", preferred: int = 8000, max_tries: int = 20) -> int:
    for p in range(preferred, preferred + max_tries):
        if not _is_port_open(host, p):
            return p
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _wait_http_ok(url: str, timeout_s: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.25)
    return False


def start_bundled_ollama(base: Path, *, ollama_url: str = "http://127.0.0.1:11434") -> subprocess.Popen | None:
    """Ensure local Ollama daemon is running using bundled portable binary/models when available."""
    if _wait_http_ok(f"{ollama_url.rstrip('/')}/api/tags", timeout_s=0.6):
        return None

    candidates = [
        base / "ollama" / "ollama.exe",
        base / "ollama" / "ollama",
    ]
    found = next((c for c in candidates if c.is_file()), None)
    if found is None:
        sys_ollama = shutil.which("ollama")
        found = Path(sys_ollama) if sys_ollama else None
    if found is None:
        return None

    env = dict(os.environ)
    models_dir = base / "models"
    if models_dir.is_dir():
        env["OLLAMA_MODELS"] = str(models_dir)
    env["OLLAMA_HOST"] = ollama_url.replace("http://", "").replace("https://", "")
    env.setdefault("OLLAMA_KEEP_ALIVE", os.environ.get("SMRITI_LLM_KEEP_ALIVE", "15m"))

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        [str(found), "serve"],
        cwd=str(found.parent),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    atexit.register(lambda: proc.poll() is None and proc.terminate())
    _wait_http_ok(f"{ollama_url.rstrip('/')}/api/tags", timeout_s=20.0)
    return proc


def _configure_environment(base: Path, internal: Path, *, demo: bool) -> None:
    data_dir = default_data_dir(base)
    os.environ.setdefault("SMRITI_DATA_DIR", str(data_dir))
    os.environ.setdefault("SMRITI_LLM_MODEL", "qwen2.5:1.5b")
    os.environ.setdefault("SMRITI_LLM_NUM_CTX", "2048")
    os.environ.setdefault("SMRITI_LLM_KEEP_ALIVE", "15m")

    # Use isolated port for bundled portable Ollama so bundled models/ weights load cleanly offline.
    if (base / "ollama" / "ollama.exe").is_file() and (base / "models").is_dir():
        os.environ.setdefault("SMRITI_OLLAMA_URL", f"http://127.0.0.1:{pick_port('127.0.0.1', preferred=11435)}")

    # Wire bundled offline HuggingFace / SentenceTransformer embeddings cache if present.
    hf_cache = base / "hf_cache"
    if hf_cache.is_dir():
        os.environ.setdefault("HF_HOME", str(hf_cache))
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(hf_cache))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    # Wire bundled portable Tesseract OCR if present (for scanned PYQ/uploaded PDFs).
    tess_dir = base / "tesseract"
    if tess_dir.is_dir():
        os.environ["PATH"] = f"{tess_dir}{os.pathsep}" + os.environ.get("PATH", "")
        tessdata = tess_dir / "tessdata"
        if tessdata.is_dir():
            os.environ.setdefault("TESSDATA_PREFIX", str(tessdata))

    for env_key, folder_name in [("SMRITI_PYQ_DIR", "pyqs"), ("SMRITI_SYLLABUS_DIR", "syllabus")]:
        if not os.environ.get(env_key):
            for candidate in (base / folder_name, internal / folder_name):
                if candidate.is_dir():
                    os.environ[env_key] = str(candidate)
                    break

    if demo:
        os.environ.setdefault("SMRITI_PASSPHRASE", "demo")


def _find_static_dist(base: Path, internal: Path) -> Path | None:
    for cand in (
        internal / "smriti" / "ui" / "web" / "dist",
        internal / "web" / "dist",
        base / "web" / "dist",
        Path(__file__).resolve().parent / "ui" / "web" / "dist",
    ):
        if (cand / "index.html").is_file():
            return cand
    return None


@contextmanager
def _redirected_stdio(log_dir: Path):
    """Redirect None stdio streams in windowed PyInstaller builds to a log file or devnull."""
    if sys.stdout is not None and sys.stderr is not None:
        yield
        return
    prev_stdout, prev_stderr = sys.stdout, sys.stderr
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "smriti-desktop.log"
        with log_path.open("a", encoding="utf-8"):
            pass
    except OSError:
        log_path = Path(os.devnull)
    try:
        with log_path.open("a", encoding="utf-8", buffering=1) as stream:
            if sys.stdout is None:
                sys.stdout = stream
            if sys.stderr is None:
                sys.stderr = stream
            yield
    finally:
        sys.stdout = prev_stdout
        sys.stderr = prev_stderr


def main(argv: list[str] | None = None) -> int:
    base = bundle_root()
    internal = internal_root()
    with _redirected_stdio(default_data_dir(base)):
        parser = argparse.ArgumentParser(prog="smriti-desktop", description="Single-click desktop launcher for Smriti AI")
        parser.add_argument("--port", type=int, default=8000)
        parser.add_argument("--no-browser", action="store_true")
        parser.add_argument("--demo", action="store_true", help="Preload fictional Alex Demo workspace on first launch")
        args = parser.parse_args(argv)

        _configure_environment(base, internal, demo=args.demo)

        # Start portable Ollama if available, then fall back to extractive mode cleanly if absent.
        from smriti.config import Settings
        from smriti.llm import list_ollama_models, ollama_status
        from smriti.llm.ollama import warm_up

        ollama_url = Settings().ollama_url
        start_bundled_ollama(base, ollama_url=ollama_url)
        installed = list_ollama_models(ollama_url)
        if installed:
            chosen = Settings().llm_model
            if not any(n == chosen or n.split(":")[0] == chosen for n in installed):
                for cand in ("qwen2.5:1.5b", "qwen2.5:3b", "qwen2.5:0.5b", installed[0]):
                    if any(n == cand or n.split(":")[0] == cand for n in installed):
                        os.environ["SMRITI_LLM_MODEL"] = cand
                        break
            ok, _ = ollama_status(Settings().llm_model, ollama_url)
            if ok:
                threading.Thread(target=lambda: warm_up(Settings().llm_model, ollama_url), daemon=True).start()
            else:
                os.environ["SMRITI_LLM"] = "extractive"
        else:
            os.environ.setdefault("SMRITI_LLM", "extractive")

        from smriti.app import build_app
        from smriti.demo import load_manifest
        from smriti.server import create_app

        app = build_app()
        if args.demo and not app.db.list_documents():
            for demo_cand in (base / "evals" / "data" / "alex_demo", internal / "alex_demo"):
                if (demo_cand / "manifest.json").is_file():
                    load_manifest(demo_cand, app)
                    break

        static_dir = _find_static_dist(base, internal)
        fastapi_app = create_app(app, static_dir=static_dir, demo_mode=args.demo)
        port = pick_port("127.0.0.1", args.port)
        url = f"http://127.0.0.1:{port}"

        if not args.no_browser:
            threading.Timer(0.9, lambda: open_browser_quietly(url)).start()

        import uvicorn

        use_colors = bool(sys.stderr and getattr(sys.stderr, "isatty", lambda: False)())
        uvicorn.run(fastapi_app, host="127.0.0.1", port=port, log_level="warning", use_colors=use_colors)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
