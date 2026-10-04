from pathlib import Path

import pytest

from smriti.app import build_app
from smriti.config import Settings
from smriti.demo import load_manifest

DATA = Path(__file__).resolve().parent.parent / "evals" / "data"


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    s = Settings()
    s.data_dir = tmp_path / "data"
    s.llm_backend = "extractive"  # tests never need a model
    s.passphrase = "test-passphrase"
    s.tracing = "off"
    return s


@pytest.fixture()
def demo_app(settings: Settings):
    app = build_app(settings)
    load_manifest(DATA / "alex_demo", app)
    return app
