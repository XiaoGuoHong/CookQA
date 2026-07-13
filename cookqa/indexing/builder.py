from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from cookqa.ingest.parser import parse_recipe
from cookqa.ingest.selection import load_selection, validate_selection
from cookqa.indexing.manifest import IndexManifest, compute_id_hash, validate_manifest
from cookqa.models import Recipe
from cookqa.retrieval.bm25 import BM25Retriever, recipe_document
from cookqa.retrieval.faiss_store import ExactVectorIndex
from cookqa.retrieval.ports import Embedder


class GraphWriter(Protocol):
    async def replace_recipes(self, recipes: list[Recipe], data_version: str) -> set[str]: ...


@dataclass(frozen=True, slots=True)
class BuildResult:
    manifest: IndexManifest
    artifact_dir: Path


class BuildPipeline:
    def __init__(self, embedder: Embedder, graph_writer: GraphWriter):
        self.embedder = embedder
        self.graph_writer = graph_writer

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
        data_version = f"{source_version[:12]}-{id_hash[:12]}"
        runtime_dir = data_dir / "runtime"
        staging_dir = runtime_dir / "builds" / str(uuid.uuid4())
        staging_dir.mkdir(parents=True, exist_ok=False)
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
            vector_index = ExactVectorIndex.build(recipe_ids, vectors)
            vector_index.save(staging_dir / "faiss.npz")

            graph_ids = await self.graph_writer.replace_recipes(recipes, data_version)
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

            indexes_dir = data_dir / "indexes"
            indexes_dir.mkdir(parents=True, exist_ok=True)
            artifact_dir = indexes_dir / data_version
            if artifact_dir.exists():
                shutil.rmtree(artifact_dir)
            os.replace(staging_dir, artifact_dir)

            processed_dir = data_dir / "processed"
            processed_dir.mkdir(parents=True, exist_ok=True)
            processed_temp = processed_dir / "recipes.jsonl.tmp"
            shutil.copyfile(artifact_dir / "recipes.jsonl", processed_temp)
            os.replace(processed_temp, processed_dir / "recipes.jsonl")

            runtime_dir.mkdir(parents=True, exist_ok=True)
            active_temp = runtime_dir / "active.json.tmp"
            active_temp.write_text(
                json.dumps({"version": data_version}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(active_temp, runtime_dir / "active.json")
            return BuildResult(manifest=manifest, artifact_dir=artifact_dir)
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise
