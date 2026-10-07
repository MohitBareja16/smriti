"""Load evaluation datasets with splits, and fingerprint them so every result names the exact data."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SPLITS = ("dev", "test", "all")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def load_split(path: Path, split: str = "dev") -> list[dict]:
    """Rows of a JSONL file for one split. Items without a `split` field count as 'dev'."""
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}")
    rows = read_jsonl(path)
    return rows if split == "all" else [r for r in rows if r.get("split", "dev") == split]


def fingerprint(data_dir: Path) -> dict:
    """SHA-256 of every file in the dataset folder (sorted), plus a combined digest."""
    data_dir = Path(data_dir)
    files = {}
    for f in sorted(p for p in data_dir.rglob("*") if p.is_file()):
        files[str(f.relative_to(data_dir))] = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
    combined = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]
    return {"combined": combined, "files": files}
