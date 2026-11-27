"""Lightweight local embedding helper for Hybrid BM25 + Vector search (stdlib/numpy/sentence-transformers)."""

from __future__ import annotations

import array
import importlib.util
import math
from collections.abc import Callable
from typing import Any


def _pack_floats(vec: list[float] | Any) -> tuple[int, bytes]:
    arr = array.array("f", (float(x) for x in vec))
    norm = math.sqrt(sum(v * v for v in arr))
    if norm > 0.0:
        arr = array.array("f", (v / norm for v in arr))
    return len(arr), arr.tobytes()


def cosine_from_blob(query_vec: bytes, candidate_vec: bytes) -> float:
    """Fast cosine similarity between L2-normalized little-endian float32 BLOBs."""
    try:
        import numpy as np

        a = np.frombuffer(query_vec, dtype=np.float32)
        b = np.frombuffer(candidate_vec, dtype=np.float32)
        if a.shape != b.shape or a.size == 0:
            return 0.0
        return float(np.dot(a, b))
    except ImportError:
        a_arr = array.array("f")
        b_arr = array.array("f")
        a_arr.frombytes(query_vec)
        b_arr.frombytes(candidate_vec)
        if len(a_arr) != len(b_arr) or not a_arr:
            return 0.0
        return sum(x * y for x, y in zip(a_arr, b_arr, strict=True))


class LocalEmbedder:
    """Lazy, process-cached local text embedder with non-fatal offline fallback."""

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        *,
        mode: str = "auto",
        encode_fn: Callable[[list[str]], list[list[float]]] | None = None,
    ) -> None:
        self.model_name = model_name
        self.mode = mode  # "auto" | "always" | "off"
        self._encode_fn = encode_fn
        self._model: Any = None
        self._checked = False
        self._available = encode_fn is not None

    @property
    def available(self) -> bool:
        if self._encode_fn is not None:
            return True
        if self.mode == "off":
            return False
        if self._checked:
            return self._available
        self._checked = True
        if importlib.util.find_spec("sentence_transformers") is None:
            self._available = False
            return False
        try:
            from sentence_transformers import SentenceTransformer

            local_only = self.mode != "always"
            self._model = SentenceTransformer(self.model_name, local_files_only=local_only)
            self._available = True
        except Exception:  # noqa: BLE001 — optional offline ML fallback must never crash core RAG
            self._model = None
            self._available = False
        return self._available

    def encode_many(self, texts: list[str]) -> list[tuple[int, bytes]]:
        if not texts or not self.available:
            return []
        if self._encode_fn is not None:
            raw_vecs = self._encode_fn(texts)
            return [_pack_floats(v) for v in raw_vecs]
        vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        out: list[tuple[int, bytes]] = []
        for row in vecs:
            out.append(_pack_floats(row.tolist() if hasattr(row, "tolist") else list(row)))
        return out

    def encode_one(self, text: str) -> bytes | None:
        encoded = self.encode_many([text])
        return encoded[0][1] if encoded else None


_CACHE: dict[tuple[str, str], LocalEmbedder] = {}


def get_embedder(*, mode: str = "auto", model_name: str = "all-MiniLM-L6-v2") -> LocalEmbedder:
    key = (mode, model_name)
    if key not in _CACHE:
        _CACHE[key] = LocalEmbedder(model_name=model_name, mode=mode)
    return _CACHE[key]
