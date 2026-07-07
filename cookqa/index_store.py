import json
from pathlib import Path
from typing import Callable, Iterable, List, Sequence, Tuple

import faiss
import numpy as np

from .models import RecipeChunk, RecipeDocument


EmbedTexts = Callable[[Sequence[str]], Sequence[Sequence[float]]]
EmbedQuery = Callable[[str], Sequence[float]]
MAX_EMBED_TEXT_CHARS = 1200


def _as_matrix(vectors: Sequence[Sequence[float]]) -> np.ndarray:
    matrix = np.asarray(vectors, dtype="float32")
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("embedding matrix must be non-empty and two-dimensional")
    faiss.normalize_L2(matrix)
    return matrix


def build_recipe_chunks(recipes: Iterable[RecipeDocument]) -> List[RecipeChunk]:
    chunks: List[RecipeChunk] = []
    for recipe in recipes:
        chunks.append(
            RecipeChunk(
                chunk_id=f"{recipe.recipe_id}#recipe",
                recipe_id=recipe.recipe_id,
                name=recipe.name,
                source_path=recipe.source_path,
                text=_compact_recipe_text(recipe),
                kind="recipe",
                ordinal=0,
            )
        )
    return chunks


def _compact_recipe_text(recipe: RecipeDocument) -> str:
    parts = [
        f"菜名：{recipe.name}",
        f"分类：{recipe.category}",
    ]
    if recipe.description:
        parts.append(f"简介：{recipe.description}")
    if recipe.difficulty:
        parts.append(f"难度：{recipe.difficulty}")
    if recipe.calories:
        parts.append(f"热量：{recipe.calories}")
    if recipe.ingredients:
        parts.append(f"原料：{'、'.join(recipe.ingredients)}")
    if recipe.tools:
        parts.append(f"工具：{'、'.join(recipe.tools)}")
    if recipe.steps:
        parts.append(f"步骤摘要：{'；'.join(recipe.summary_steps())}")
    return "\n".join(parts)[:MAX_EMBED_TEXT_CHARS]


def build_step_chunks(recipes: Iterable[RecipeDocument]) -> List[RecipeChunk]:
    chunks: List[RecipeChunk] = []
    for recipe in recipes:
        for index, step in enumerate(recipe.steps, start=1):
            chunks.append(
                RecipeChunk(
                    chunk_id=f"{recipe.recipe_id}#step-{index}",
                    recipe_id=recipe.recipe_id,
                    name=recipe.name,
                    source_path=recipe.source_path,
                    text=step,
                    kind="step",
                    ordinal=index,
                )
            )
    return chunks


class FaissIndexStore:
    def __init__(self, index: faiss.Index, payloads: List[RecipeChunk]):
        self.index = index
        self.payloads = payloads

    @classmethod
    def build(
        cls,
        chunks: Sequence[RecipeChunk],
        embed_texts: EmbedTexts,
        index_path: Path,
        payload_path: Path,
    ) -> None:
        if not chunks:
            raise ValueError("cannot build FAISS index without chunks")
        vectors = _as_matrix(embed_texts([chunk.text for chunk in chunks]))
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(index_path))
        payload_path.write_text(
            json.dumps(
                [chunk.model_dump() for chunk in chunks],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, index_path: Path, payload_path: Path) -> "FaissIndexStore":
        if not index_path.exists() or not payload_path.exists():
            raise FileNotFoundError("FAISS index or payload file is missing")
        index = faiss.read_index(str(index_path))
        raw_payloads = json.loads(payload_path.read_text(encoding="utf-8"))
        return cls(index=index, payloads=[RecipeChunk(**item) for item in raw_payloads])

    def search(
        self,
        query: str,
        embed_query: EmbedQuery,
        top_k: int,
    ) -> List[Tuple[RecipeChunk, float]]:
        query_matrix = _as_matrix([embed_query(query)])
        scores, indexes = self.index.search(query_matrix, top_k)
        results: List[Tuple[RecipeChunk, float]] = []
        for score, index in zip(scores[0].tolist(), indexes[0].tolist()):
            if index < 0:
                continue
            results.append((self.payloads[index], float(score)))
        return results
