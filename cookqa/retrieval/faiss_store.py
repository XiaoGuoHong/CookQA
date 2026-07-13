from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import numpy as np

from cookqa.models import QueryPlan, RankedCandidate
from cookqa.retrieval.ports import Embedder


def _require_faiss():
    try:
        import faiss
    except ImportError as exc:
        raise RuntimeError("FAISS 不可用，请安装 faiss-cpu") from exc
    return faiss


def _validate_recipe_ids(recipe_ids: list[str]) -> None:
    if not recipe_ids or any(not isinstance(item, str) or not item for item in recipe_ids):
        raise ValueError("recipe_ids 必须是非空字符串列表")
    if len(recipe_ids) != len(set(recipe_ids)):
        raise ValueError("recipe_ids 包含重复值")


def _as_matrix(vectors: np.ndarray, recipe_count: int) -> np.ndarray:
    array = np.asarray(vectors, dtype=np.float32)
    if array.ndim != 2 or array.shape[0] != recipe_count or array.shape[1] == 0:
        raise ValueError("向量矩阵形状与 recipe_ids 不一致")
    if not np.isfinite(array).all():
        raise ValueError("向量必须是有限数值")
    if np.any(np.linalg.norm(array, axis=1) == 0):
        raise ValueError("向量不能为零向量")
    return np.ascontiguousarray(array)


class FaissVectorIndex:
    def __init__(self, recipe_ids: list[str], index: Any):
        faiss = _require_faiss()
        _validate_recipe_ids(recipe_ids)
        if not isinstance(index, faiss.IndexFlatIP):
            raise ValueError("FAISS 索引必须是 IndexFlatIP")
        if int(index.d) <= 0:
            raise ValueError("FAISS 索引维度必须为正数")
        if int(index.ntotal) != len(recipe_ids):
            raise ValueError("FAISS 向量数量与 recipe_ids 数量不一致")
        self.recipe_ids = list(recipe_ids)
        self.index = index
        self.dimension = int(index.d)

    @classmethod
    def build(cls, recipe_ids: list[str], vectors: np.ndarray) -> FaissVectorIndex:
        faiss = _require_faiss()
        _validate_recipe_ids(recipe_ids)
        array = _as_matrix(vectors, len(recipe_ids))
        faiss.normalize_L2(array)
        index = faiss.IndexFlatIP(array.shape[1])
        index.add(array)
        return cls(recipe_ids, index)

    def search(self, vector: np.ndarray, limit: int) -> list[tuple[str, float]]:
        if limit <= 0:
            raise ValueError("limit 必须大于 0")
        query = np.asarray(vector, dtype=np.float32)
        if query.ndim != 1 or query.shape[0] != self.dimension:
            raise ValueError("查询向量维度与索引不一致")
        query = _as_matrix(query.reshape(1, -1), 1)
        faiss = _require_faiss()
        faiss.normalize_L2(query)
        scores, indices = self.index.search(query, min(limit, len(self.recipe_ids)))
        return [
            (self.recipe_ids[int(index)], float(score))
            for score, index in zip(scores[0], indices[0], strict=True)
            if 0 <= int(index) < len(self.recipe_ids)
        ]

    def save(self, index_path: Path, ids_path: Path) -> None:
        faiss = _require_faiss()
        index_path.parent.mkdir(parents=True, exist_ok=True)
        ids_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(index_path))
        ids_path.write_text(
            json.dumps(self.recipe_ids, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, index_path: Path, ids_path: Path) -> FaissVectorIndex:
        faiss = _require_faiss()
        try:
            index = faiss.read_index(str(index_path))
        except Exception as exc:
            raise RuntimeError("FAISS 索引无法读取") from exc
        try:
            recipe_ids = json.loads(ids_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("FAISS recipe_id 映射无法读取") from exc
        if not isinstance(recipe_ids, list):
            raise ValueError("FAISS recipe_id 映射格式无效")
        return cls(recipe_ids, index)


class FaissRetriever:
    name = "faiss"

    def __init__(
        self,
        index: FaissVectorIndex,
        embedder: Embedder,
        timeout_seconds: float = 0.75,
    ):
        self.index = index
        self.embedder = embedder
        self.timeout_seconds = timeout_seconds

    async def search(self, plan: QueryPlan, limit: int) -> list[RankedCandidate]:
        vector = await asyncio.wait_for(
            self.embedder.embed(plan.normalized_query), timeout=self.timeout_seconds
        )
        return [
            RankedCandidate(
                recipe_id=recipe_id,
                score=score,
                source=self.name,
                reasons=["语义相似"],
            )
            for recipe_id, score in self.index.search(
                np.asarray(vector, dtype=np.float32), limit
            )
        ]
