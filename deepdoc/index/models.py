"""Free local models (ONNX on CPU, via fastembed). Loaded once, on first use."""
from __future__ import annotations

import threading

import numpy as np

from .. import config

_lock = threading.Lock()
_embedder = None
_reranker = None


def embedder():
    global _embedder
    with _lock:
        if _embedder is None:
            from fastembed import TextEmbedding
            _embedder = TextEmbedding(config.EMBED_MODEL, cache_dir=str(config.MODEL_DIR), threads=config.MODEL_THREADS)
        return _embedder


def reranker():
    global _reranker
    with _lock:
        if _reranker is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
            _reranker = TextCrossEncoder(config.RERANK_MODEL, cache_dir=str(config.MODEL_DIR), threads=config.MODEL_THREADS)
        return _reranker


def _norm(m: np.ndarray) -> np.ndarray:
    return (m / np.clip(np.linalg.norm(m, axis=1, keepdims=True), 1e-9, None)).astype(np.float32)


def embed_passages(texts: list[str]) -> np.ndarray:
    return _norm(np.array(list(embedder().passage_embed(texts, batch_size=config.EMBED_BATCH))))


def embed_query(text: str) -> np.ndarray:
    return _norm(np.array(list(embedder().query_embed([text]))))[0]


def rerank(query: str, docs: list[str]) -> list[float]:
    if not docs:
        return []
    return [float(s) for s in reranker().rerank(query, docs, batch_size=config.EMBED_BATCH)]
