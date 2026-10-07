"""Grounding checks: is a sentence of the answer supported by the retrieved evidence? (issue #9)

Four rules, compared in the `grounding_benchmark` experiment:

    lexical    share of the sentence's content words found in the evidence >= t   (no model)
    nli        NLI entailment probability against the best evidence passage >= t
    embedding  cosine similarity to the most similar evidence sentence >= t
    hybrid     not contradicted by the evidence (NLI) AND on-topic (embedding similarity >= t)

`lexical` needs nothing extra. The others need `pip install -e ".[ml]"` and download small CPU
models on first use: an NLI cross-encoder and a sentence-embedding model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from smriti.decision.text import norm_set
from smriti.types import Decision

NLI_MODEL = "cross-encoder/nli-deberta-v3-xsmall"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RULES = ("lexical", "nli", "embedding", "hybrid")
DEFAULT_THRESHOLDS = {"lexical": 0.6, "nli": 0.5, "embedding": 0.6, "hybrid": 0.6, "hybrid_contradiction": 0.5}

_BOUNDARY = re.compile(r"[.!?]\s+")
_LIST_NUMBER = re.compile(r"(?:^|\s)\d{1,2}$")  # "2." in "… (3 papers) 2. Paging" is a list marker


class MissingModelDependencyError(RuntimeError):
    pass


def sentence_spans(text: str) -> list[str]:
    """Split into sentences: one per line, then at . ! ? — but not after a list number like "2."."""
    out: list[str] = []
    for line in text.splitlines():
        start = 0
        for m in _BOUNDARY.finditer(line):
            if _LIST_NUMBER.search(line[start:m.start()]):
                continue
            out.append(line[start:m.end()].strip())
            start = m.end()
        if line[start:].strip():
            out.append(line[start:].strip())
    return [s for s in out if s]


def split_sentences(text: str) -> list[str]:
    return [s.strip(" -*#\t") for s in sentence_spans(text) if len(s.strip(" -*#\t")) > 3]


# ---- signals -------------------------------------------------------------------------------
def lexical_coverage(claim: str, evidence: list[str]) -> float:
    claim_toks = norm_set(claim)
    if not claim_toks:
        return 1.0
    return len(claim_toks & norm_set("\n".join(evidence))) / len(claim_toks)


@lru_cache(maxsize=2)
def _cross_encoder(name: str):
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise MissingModelDependencyError('NLI grounding needs: pip install -e ".[ml]"') from exc
    return CrossEncoder(name, device="cpu")


@lru_cache(maxsize=2)
def _embedder(name: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise MissingModelDependencyError('Embedding grounding needs: pip install -e ".[ml]"') from exc
    return SentenceTransformer(name, device="cpu")


def nli_signals(claims: list[str], evidence: list[str], model: str = NLI_MODEL) -> list[dict]:
    """Per claim: entailment of the best passage, and the strongest contradiction from any passage."""
    if not claims or not evidence:
        return [{"entail": 0.0, "contradict": 0.0} for _ in claims]
    ce = _cross_encoder(model)
    labels = {v.lower(): k for k, v in ce.model.config.id2label.items()}
    pairs = [(p, c) for c in claims for p in evidence]
    probs = ce.predict(pairs, apply_softmax=True, batch_size=32, show_progress_bar=False)
    out, n = [], len(evidence)
    for i in range(len(claims)):
        rows = probs[i * n:(i + 1) * n]
        out.append({"entail": float(max(r[labels["entailment"]] for r in rows)),
                    "contradict": float(max(r[labels["contradiction"]] for r in rows))})
    return out


def embedding_similarity(claims: list[str], evidence: list[str], model: str = EMBED_MODEL) -> list[float]:
    """Per claim: cosine similarity to the most similar evidence sentence."""
    sentences = [s for e in evidence for s in split_sentences(e)]
    if not claims or not sentences:
        return [0.0 for _ in claims]
    emb = _embedder(model)
    c = emb.encode(claims, normalize_embeddings=True, show_progress_bar=False)
    s = emb.encode(sentences, normalize_embeddings=True, show_progress_bar=False)
    return [float(x) for x in (c @ s.T).max(axis=1)]


# ---- decisions -----------------------------------------------------------------------------
@dataclass
class Grounder:
    """Decides, sentence by sentence, whether an answer is supported by the evidence passages."""

    rule: str = "lexical"
    thresholds: dict = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))
    nli_model: str = NLI_MODEL
    embed_model: str = EMBED_MODEL

    def __post_init__(self) -> None:
        if self.rule not in RULES:
            raise ValueError(f"grounding rule must be one of {RULES}")
        self.thresholds = {**DEFAULT_THRESHOLDS, **self.thresholds}

    @property
    def name(self) -> str:
        return self.rule

    def signals(self, claims: list[str], evidence: list[str]) -> list[dict]:
        sig = [{"lexical": lexical_coverage(c, evidence)} for c in claims]
        if self.rule in ("nli", "hybrid"):
            for s, n in zip(sig, nli_signals(claims, evidence, self.nli_model)):
                s.update(n)
        if self.rule in ("embedding", "hybrid"):
            for s, e in zip(sig, embedding_similarity(claims, evidence, self.embed_model)):
                s["embedding"] = e
        return sig

    def decide(self, signal: dict) -> Decision:
        t = self.thresholds
        if self.rule == "lexical":
            score = signal["lexical"]
            ok = score >= t["lexical"]
        elif self.rule == "nli":
            score = signal["entail"]
            ok = score >= t["nli"]
        elif self.rule == "embedding":
            score = signal["embedding"]
            ok = score >= t["embedding"]
        else:  # hybrid: on-topic and not contradicted
            score = signal["embedding"] * (1 - signal["contradict"])
            ok = signal["embedding"] >= t["hybrid"] and signal["contradict"] < t["hybrid_contradiction"]
        p = max(0.0, min(1.0, score))
        return Decision("yes" if ok else "no", p if ok else 1 - p, {"yes": p, "no": 1 - p})

    def check(self, claims: list[str], evidence: list[str]) -> list[Decision]:
        return [self.decide(s) for s in self.signals(claims, evidence)]
