"""Capture everything needed to reproduce a run: code version, platform, models, settings."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
import urllib.request
from dataclasses import asdict
from pathlib import Path

import smriti
from smriti.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                              timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _ollama_model_digest(settings: Settings) -> str | None:
    if settings.llm_backend != "ollama":
        return None
    try:
        with urllib.request.urlopen(f"{settings.ollama_url}/api/tags", timeout=3) as resp:
            for m in json.loads(resp.read()).get("models", []):
                if m["name"] in (settings.llm_model, f"{settings.llm_model}:latest"):
                    return m.get("digest")
    except (OSError, ValueError):
        return None
    return None


def capture(settings: Settings) -> dict:
    s = asdict(settings)
    s.pop("passphrase", None)  # never write secrets into results
    s["data_dir"] = "<temporary>"
    return {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "smriti_version": smriti.__version__,
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "llm_model_digest": _ollama_model_digest(settings),
        "settings": s,
    }
