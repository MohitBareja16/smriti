"""Load the fictional 'Alex Demo' student into a data directory (used by `parag demo` and the evals)."""

from __future__ import annotations

import json
from pathlib import Path

from parag.app import App
from parag.ingest import IngestResult, ingest_file


def load_manifest(dataset_dir: Path, app: App) -> list[IngestResult]:
    manifest = json.loads((dataset_dir / "manifest.json").read_text())
    return [
        ingest_file(dataset_dir / entry["path"], app.db, app.vault, course=entry.get("course"),
                    kind=entry.get("kind"))
        for entry in manifest["files"]
    ]
