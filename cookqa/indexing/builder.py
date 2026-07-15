from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from cookqa.indexing.activation import (
    activate_version,
    read_active_version,
    swap_to_previous,
)
from cookqa.indexing.manifest import IndexManifest, compute_id_hash, validate_manifest
from cookqa.ingest.parser import parse_recipe
from cookqa.ingest.selection import load_selection, validate_selection
from cookqa.models import Recipe
from cookqa.retrieval.bm25 import BM25Retriever, recipe_document
from cookqa.retrieval.faiss_store import FaissVectorIndex
from cookqa.retrieval.ports import Embedder

logger = logging.getLogger(__name__)


class GraphWriter(Protocol):
    async def ensure_schema(self) -> None: ...

    async def write_version(self, recipes: list[Recipe], data_version: str) -> None: ...

    async def validate_version(
        self,
        recipes: list[Recipe],
        data_version: str,
    ) -> set[str]: ...

    async def delete_version(self, data_version: str) -> None: ...

    async def cleanup_versions(self, keep_versions: set[str]) -> None: ...


@dataclass(frozen=True, slots=True)
class BuildResult:
    manifest: IndexManifest
    artifact_dir: Path


def _load_recipes(path: Path) -> list[Recipe]:
    return [
        Recipe.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _cleanup_local_versions(indexes_dir: Path, keep_versions: set[str]) -> None:
    if not indexes_dir.is_dir():
        return
    for path in indexes_dir.iterdir():
        if path.is_dir() and path.name not in keep_versions:
            shutil.rmtree(path)


class BuildPipeline:
    def __init__(self, embedder: Embedder, graph_writer: GraphWriter):
        self.embedder = embedder
        self.graph_writer = graph_writer

    async def _validate_artifact(self, artifact_dir: Path) -> BuildResult:
        manifest = IndexManifest.load(artifact_dir / "index-manifest.json")
        recipes = _load_recipes(artifact_dir / "recipes.jsonl")
        bm25 = BM25Retriever.load(artifact_dir / "bm25.json")
        vector_index = FaissVectorIndex.load(
            artifact_dir / "faiss.index",
            artifact_dir / "faiss.ids.json",
        )
        graph_ids = await self.graph_writer.validate_version(
            recipes,
            manifest.data_version,
        )
        validate_manifest(
            manifest,
            bm25_ids=set(bm25.recipe_ids),
            faiss_ids=set(vector_index.recipe_ids),
            graph_ids=graph_ids,
            embedding_dimension=vector_index.dimension,
        )
        return BuildResult(manifest=manifest, artifact_dir=artifact_dir)

    async def build(
        self,
        source_root: Path,
        selection_path: Path,
        aliases_path: Path,
        source_version: str,
        embedding_model: str,
        data_dir: Path,
    ) -> BuildResult:
        entries = load_selection(selection_path)
        paths = validate_selection(source_root, entries)
        aliases = json.loads(aliases_path.read_text(encoding="utf-8"))
        recipes = [
            parse_recipe(path, source_root, source_version, aliases)
            for path in paths
        ]
        recipe_ids = [recipe.recipe_id for recipe in recipes]
        if len(recipe_ids) != len(set(recipe_ids)):
            raise ValueError("解析结果包含重复 recipe_id")

        id_hash = compute_id_hash(recipe_ids)
        data_version = (
            f"{source_version[:12]}-{id_hash[:12]}-{uuid.uuid4().hex[:8]}"
        )
        previous = read_active_version(data_dir)
        runtime_dir = data_dir / "runtime"
        staging_dir = runtime_dir / "builds" / str(uuid.uuid4())
        staging_dir.mkdir(parents=True, exist_ok=False)
        indexes_dir = data_dir / "indexes"
        artifact_dir = indexes_dir / data_version
        candidate_started = False
        activated = False
        try:
            recipes_path = staging_dir / "recipes.jsonl"
            recipes_path.write_text(
                "".join(
                    json.dumps(recipe.model_dump(), ensure_ascii=False) + "\n"
                    for recipe in recipes
                ),
                encoding="utf-8",
            )

            bm25 = BM25Retriever.build(recipes)
            bm25.save(staging_dir / "bm25.json")

            vectors = np.asarray(
                [await self.embedder.embed(recipe_document(recipe)) for recipe in recipes],
                dtype=np.float32,
            )
            vector_index = FaissVectorIndex.build(recipe_ids, vectors)
            vector_index.save(
                staging_dir / "faiss.index",
                staging_dir / "faiss.ids.json",
            )

            await self.graph_writer.ensure_schema()
            candidate_started = True
            await self.graph_writer.write_version(recipes, data_version)
            graph_ids = await self.graph_writer.validate_version(recipes, data_version)
            manifest = IndexManifest(
                data_version=data_version,
                recipe_count=len(recipes),
                recipe_id_hash=id_hash,
                embedding_model=embedding_model,
                embedding_dimension=vector_index.dimension,
                bm25_version="1",
                faiss_version="1",
                graph_version=data_version,
            )
            validate_manifest(
                manifest,
                bm25_ids=set(bm25.recipe_ids),
                faiss_ids=set(vector_index.recipe_ids),
                graph_ids=graph_ids,
                embedding_dimension=vector_index.dimension,
            )
            manifest.save(staging_dir / "index-manifest.json")

            indexes_dir.mkdir(parents=True, exist_ok=True)
            if artifact_dir.exists():
                raise FileExistsError(f"候选版本目录已存在: {data_version}")
            os.replace(staging_dir, artifact_dir)

            processed_dir = data_dir / "processed"
            processed_dir.mkdir(parents=True, exist_ok=True)
            processed_temp = processed_dir / "recipes.jsonl.tmp"
            shutil.copyfile(artifact_dir / "recipes.jsonl", processed_temp)
            os.replace(processed_temp, processed_dir / "recipes.jsonl")

            activate_version(
                data_dir,
                data_version,
                previous.version if previous is not None else None,
            )
            activated = True

            keep_versions = {data_version}
            if previous is not None:
                keep_versions.add(previous.version)
            try:
                await self.graph_writer.cleanup_versions(keep_versions)
            except Exception as exc:
                logger.warning(
                    "Neo4j 历史版本清理失败 version=%s error=%s",
                    data_version,
                    exc.__class__.__name__,
                )
            try:
                _cleanup_local_versions(indexes_dir, keep_versions)
            except Exception as exc:
                logger.warning(
                    "本地历史版本清理失败 version=%s error=%s",
                    data_version,
                    exc.__class__.__name__,
                )
            return BuildResult(manifest=manifest, artifact_dir=artifact_dir)
        except Exception:
            if not activated and candidate_started:
                try:
                    await self.graph_writer.delete_version(data_version)
                except Exception as exc:
                    logger.warning(
                        "Neo4j 候选版本清理失败 version=%s error=%s",
                        data_version,
                        exc.__class__.__name__,
                    )
            if not activated and artifact_dir.is_dir():
                shutil.rmtree(artifact_dir, ignore_errors=True)
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

    async def rollback(self, data_dir: Path) -> BuildResult:
        active = read_active_version(data_dir)
        if active is None or active.previous_version is None:
            raise ValueError("没有可回滚的上一版本")
        artifact_dir = data_dir / "indexes" / active.previous_version
        result = await self._validate_artifact(artifact_dir)
        swap_to_previous(data_dir)
        return result
