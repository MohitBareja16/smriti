"""Wire all modules together. The CLI, UI and evals all start here."""

from __future__ import annotations

from dataclasses import dataclass

from smriti.config import Settings
from smriti.decision import get_engine
from smriti.llm import get_reasoner
from smriti.observability import setup_tracing
from smriti.orchestrator import Orchestrator
from smriti.storage import Database, get_embedder
from smriti.vault import Vault


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
    embedder = (
        get_embedder(mode=settings.hybrid_search, model_name=settings.embed_model)
        if settings.hybrid_search != "off"
        else None
    )
    db = Database(settings.db_path, embedder=embedder)
    vault = Vault(settings.vault_dir, settings.passphrase)
    orchestrator = Orchestrator(settings, db, vault, get_engine(settings.s1_engine), get_reasoner(settings))
    return App(settings, db, vault, orchestrator)
