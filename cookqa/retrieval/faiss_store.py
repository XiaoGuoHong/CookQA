from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np

from cookqa.models import QueryPlan, RankedCandidate
from cookqa.retrieval.ports import Embedder


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("向量不能为零向量")
    return vectors / norms


class ExactVectorIndex:
    """Recipe-level exact cosine index used by the FAISS adapter and tests."""

    def __init__(self, recipe_ids: list[str], vectors: np.ndarray):
        self.recipe_ids = recipe_ids
        self.vectors = vectors.astype(np.float32, copy=False)
        self.dimension = int(self.vectors.shape[1]) if self.vectors.ndim == 2 else 0

    @classmethod
    def build(cls, recipe_ids: list[str], vectors: np.ndarray) -> "ExactVectorIndex":
        array = np.asarray(vectors, dtype=np.float32)
        if array.ndim != 2 or array.shape[0] != len(recipe_ids) or array.shape[1] == 0:
            raise ValueError("向量矩阵形状与 recipe_ids 不一致")
        return cls(recipe_ids, _normalize(array))

    def search(self, vector: np.ndarray, limit: int) -> list[tuple[str, float]]:
        query = np.asarray(vector, dtype=np.float32)
        if query.ndim != 1 or query.shape[0] != self.dimension:
            raise ValueError("查询向量维度与索引不一致")
        query = _normalize(query.reshape(1, -1))[0]
        scores = self.vectors @ query
        order = np.argsort(-scores, kind="stable")[:limit]
        return [(self.recipe_ids[index], float(scores[index])) for index in order]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, recipe_ids=np.asarray(self.recipe_ids), vectors=self.vectors)

    @classmethod
    def load(cls, path: Path) -> "ExactVectorIndex":
        with np.load(path, allow_pickle=False) as payload:
            return cls(list(payload["recipe_ids"].astype(str)), payload["vectors"])


class FaissRetriever:
    name = "faiss"

    def __init__(self, index: ExactVectorIndex, embedder: Embedder, timeout_seconds: float = 0.75):
        self.index = index
        self.embedder = embedder
        self.timeout_seconds = timeout_seconds

    async def search(self, plan: QueryPlan, limit: int) -> list[RankedCandidate]:
        vector = await asyncio.wait_for(
            self.embedder.embed(plan.normalized_query), timeout=self.timeout_seconds
        )
        return [
            RankedCandidate(recipe_id=recipe_id, score=score, source=self.name, reasons=["语义相似"])
            for recipe_id, score in self.index.search(np.asarray(vector, dtype=np.float32), limit)
        ]
