"""Wire all modules together. The CLI, UI and evals all start here."""

from __future__ import annotations

from dataclasses import dataclass

from parag.config import Settings
from parag.decision import get_engine
from parag.llm import get_reasoner
from parag.observability import setup_tracing
from parag.orchestrator import Orchestrator
from parag.storage import Database
from parag.vault import Vault


@dataclass
class App:
    settings: Settings
    db: Database
    vault: Vault
    orchestrator: Orchestrator


def build_app(settings: Settings | None = None) -> App:
    settings = settings or Settings()
    settings.ensure_dirs()
    setup_tracing(settings.tracing)
    db = Database(settings.db_path)
    vault = Vault(settings.vault_dir, settings.passphrase)
    orchestrator = Orchestrator(settings, db, vault, get_engine(settings.s1_engine), get_reasoner(settings))
    return App(settings, db, vault, orchestrator)
