"""Load the fictional 'Alex Demo' student into a data directory (used by `smriti demo` and the evals)."""

from __future__ import annotations

import json
from pathlib import Path

from smriti.app import App
from smriti.ingest import IngestResult, ingest_file


def load_manifest(dataset_dir: Path, app: App) -> list[IngestResult]:
    manifest = json.loads((dataset_dir / "manifest.json").read_text())
    return [
        ingest_file(dataset_dir / entry["path"], app.db, app.vault, course=entry.get("course"),
                    semester=entry.get("semester"),
                    kind=entry.get("kind"))
        for entry in manifest["files"]
    ]
