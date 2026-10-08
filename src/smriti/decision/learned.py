"""Learned System-1 routers built on small open-source models (issue #20, RQ5).

    CascadeRouter    rules first; when the rules are unsure (p < 0.5) the embedding router decides. Rules
                     are precise but miss paraphrases; the learned router covers those (LOG 2026-10-09).
    EmbeddingRouter  sentence embeddings (default all-MiniLM-L6-v2) + multinomial logistic regression,
                     trained in seconds on CPU; a temperature is fitted on out-of-fold predictions so the
                     confidences are calibrated (System 1 answers alone only when confident).
    ZeroShotRouter   an NLI cross-encoder scores "This question is about <intent description>" for every
                     intent. Needs no training data.

Only `route` is learned. Injection checks stay with the rules engine (benchmark: #6), and grounding
uses `smriti.decision.grounding`. Needs `pip install -e ".[ml]"` (numpy + sentence-transformers).
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from smriti.decision.rules import RulesEngine
from smriti.types import INTENTS, Decision

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
NLI_MODEL = "cross-encoder/nli-deberta-v3-xsmall"
MODELS_DIR = Path("~/.smriti/models").expanduser()

INTENT_DESCRIPTIONS = {
    "fact_lookup": "a specific personal fact, like an exam date, a grade, a score, a roll number or a deadline",
    "fetch_doc": "opening, sending or downloading one of my documents or files",
    "explain": "explaining or defining a concept from my study notes or books",
    "compare": "comparing two things or the difference between them",
    "exam_prep": "past exam papers, frequently asked questions or what to revise for an exam",
    "connect": "connections between my courses, skills, projects and certificates",
    "other": "something unrelated to my studies or documents, like small talk or general questions",
}


def _np():
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError('Learned routers need: pip install -e ".[ml]"') from exc
    return np


def sentence_embedder(model: str = EMBED_MODEL) -> Callable[[Sequence[str]], object]:
    from smriti.decision.grounding import _embedder

    st = _embedder(model)
    return lambda texts: st.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)


def _decision(probs: dict[str, float]) -> Decision:
    label = max(probs, key=probs.get)
    return Decision(label=label, probability=probs[label], probs=probs)


class _RulesGuards:
    """Learned routers decide the intent; the other System-1 decisions come from the rules engine."""

    _rules = RulesEngine()

    def is_injection(self, text: str) -> Decision:
        return self._rules.is_injection(text)

    def is_supported(self, claim: str, evidence: str) -> Decision:
        return self._rules.is_supported(claim, evidence)


class EmbeddingRouter(_RulesGuards):
    name = "embedding"

    # Defaults chosen by 5-fold CV on the dev router data (l2 1e-2 underfits: 59% vs 71%); see LOG.
    def __init__(self, embed: Callable[[Sequence[str]], object] | None = None, model: str = EMBED_MODEL,
                 l2: float = 1e-3, epochs: int = 1000, lr: float = 2.0):
        self.model, self.l2, self.epochs, self.lr = model, l2, epochs, lr
        self._embed = embed
        self.labels: list[str] = list(INTENTS)
        self.W = self.b = None
        self.temperature = 1.0

    @property
    def embed(self):
        if self._embed is None:
            self._embed = sentence_embedder(self.model)
        return self._embed

    # ---- training ----------------------------------------------------------------------------
    def _train(self, X, y):
        np = _np()
        n, d = X.shape
        k = len(self.labels)
        W, b = np.zeros((d, k)), np.zeros(k)
        Y = np.eye(k)[y]
        for _ in range(self.epochs):  # full-batch gradient descent on cross-entropy + L2
            P = self._softmax(X @ W + b)
            W -= self.lr * (X.T @ (P - Y) / n + self.l2 * W)
            b -= self.lr * (P - Y).mean(axis=0)
        return W, b

    @staticmethod
    def _softmax(Z):
        np = _np()
        Z = Z - Z.max(axis=1, keepdims=True)
        E = np.exp(Z)
        return E / E.sum(axis=1, keepdims=True)

    def fit(self, questions: Sequence[str], labels: Sequence[str], calibrate: bool = True, folds: int = 5,
            seed: int = 0) -> EmbeddingRouter:
        np = _np()
        self.labels = sorted(set(labels) | set(INTENTS), key=list(INTENTS).index)
        X = np.asarray(self.embed(questions), dtype=float)
        y = np.array([self.labels.index(lab) for lab in labels])
        self.temperature = 1.0
        if calibrate and len(questions) >= 2 * folds:
            # out-of-fold logits -> pick the temperature with the lowest negative log-likelihood
            logits = np.zeros((len(y), len(self.labels)))
            for f in fold_indices(list(labels), folds, seed):
                train = np.setdiff1d(np.arange(len(y)), f)
                W, b = self._train(X[train], y[train])
                logits[f] = X[f] @ W + b
            grid = [0.25, 0.35, 0.5, 0.7, 1.0, 1.4, 2.0, 3.0]
            nll = [-np.log(self._softmax(logits / t)[np.arange(len(y)), y] + 1e-12).mean() for t in grid]
            self.temperature = grid[int(np.argmin(nll))]
        self.W, self.b = self._train(X, y)
        return self

    # ---- inference ---------------------------------------------------------------------------
    def route(self, question: str) -> Decision:
        if self.W is None:
            raise RuntimeError("EmbeddingRouter is not trained. Run: smriti train-router")
        np = _np()
        x = np.asarray(self.embed([question]), dtype=float)
        p = self._softmax((x @ self.W + self.b) / self.temperature)[0]
        return _decision({lab: float(v) for lab, v in zip(self.labels, p)})

    # ---- persistence -------------------------------------------------------------------------
    def save(self, path: Path) -> Path:
        np = _np()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, W=self.W, b=self.b)
        path.with_suffix(".json").write_text(json.dumps(
            {"model": self.model, "labels": self.labels, "temperature": self.temperature,
             "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=2))
        return path

    @classmethod
    def load(cls, path: Path, embed=None) -> EmbeddingRouter:
        np = _np()
        path = Path(path)
        meta = json.loads(path.with_suffix(".json").read_text())
        r = cls(embed=embed, model=meta["model"])
        data = np.load(path)
        r.W, r.b, r.labels, r.temperature = data["W"], data["b"], meta["labels"], meta["temperature"]
        return r


class CascadeRouter(_RulesGuards):
    name = "cascade"

    def __init__(self, learned: EmbeddingRouter, threshold: float = 0.5):
        self.learned, self.threshold = learned, threshold
        self.rules = RulesEngine()

    def route(self, question: str) -> Decision:
        d = self.rules.route(question)
        return d if d.probability >= self.threshold else self.learned.route(question)


class ZeroShotRouter(_RulesGuards):
    name = "zeroshot"

    def __init__(self, model: str = NLI_MODEL, descriptions: dict[str, str] | None = None,
                 temperature: float = 1.0):
        self.model, self.temperature = model, temperature
        self.descriptions = descriptions or INTENT_DESCRIPTIONS

    def route(self, question: str) -> Decision:
        from smriti.decision.grounding import _cross_encoder

        ce = _cross_encoder(self.model)
        entail = {v.lower(): k for k, v in ce.model.config.id2label.items()}["entailment"]
        labels = list(self.descriptions)
        logits = ce.predict([(question, f"This question is about {self.descriptions[lab]}.") for lab in labels],
                            show_progress_bar=False)
        scores = [float(row[entail]) / self.temperature for row in logits]
        m = max(scores)
        exps = [math.exp(s - m) for s in scores]
        return _decision({lab: e / sum(exps) for lab, e in zip(labels, exps)})


def fold_indices(labels: list[str], folds: int, seed: int = 0) -> list[list[int]]:
    """Stratified folds: each intent's items are spread round-robin over the folds (deterministic)."""
    import random

    rng = random.Random(seed)
    out: list[list[int]] = [[] for _ in range(folds)]
    by_label: dict[str, list[int]] = {}
    for i, lab in enumerate(labels):
        by_label.setdefault(lab, []).append(i)
    offset = 0
    for lab in sorted(by_label):
        idx = by_label[lab]
        rng.shuffle(idx)
        for j, i in enumerate(idx):
            out[(offset + j) % folds].append(i)
        offset += len(idx)
    return [sorted(f) for f in out]


def training_data(data_dir: Path, split: str = "dev") -> tuple[list[str], list[str]]:
    """Labelled router questions: router.jsonl + the intents of qa.jsonl."""
    from smriti.research.datasets import load_split

    rows = []
    for name in ("router.jsonl", "qa.jsonl"):
        if (Path(data_dir) / name).exists():
            rows += load_split(Path(data_dir) / name, split)
    return [r["question"] for r in rows], [r["intent"] for r in rows]


def default_model_path(name: str = "router-embedding") -> Path:
    return MODELS_DIR / f"{name}.npz"
