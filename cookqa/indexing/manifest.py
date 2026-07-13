from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Set
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ManifestMismatch(RuntimeError):
    pass


class IndexManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    data_version: str
    recipe_count: int = Field(ge=1)
    recipe_id_hash: str
    embedding_model: str
    embedding_dimension: int = Field(gt=0)
    bm25_version: str
    faiss_version: str
    graph_version: str

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(self.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> IndexManifest:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


def compute_id_hash(recipe_ids: Iterable[str]) -> str:
    canonical = "\n".join(sorted(set(recipe_ids)))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_manifest(
    manifest: IndexManifest,
    bm25_ids: Set[str],
    faiss_ids: Set[str],
    graph_ids: Set[str],
    embedding_dimension: int,
) -> None:
    expected_hash = manifest.recipe_id_hash
    named_sets = {"BM25": bm25_ids, "FAISS": faiss_ids, "Neo4j": graph_ids}
    for name, ids in named_sets.items():
        if len(ids) != manifest.recipe_count or compute_id_hash(ids) != expected_hash:
            raise ManifestMismatch(f"{name} recipe_id 集合与版本清单不一致")
    if embedding_dimension != manifest.embedding_dimension:
        raise ManifestMismatch("FAISS 向量维度与版本清单不一致")
    if manifest.graph_version != manifest.data_version:
        raise ManifestMismatch("Neo4j 数据版本与版本清单不一致")
