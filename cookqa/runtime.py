from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from cookqa.config import Settings
from cookqa.generation.ollama import OllamaClient
from cookqa.indexing.manifest import IndexManifest, ManifestMismatch, validate_manifest
from cookqa.models import ComponentStatus, ReadinessReport, Recipe
from cookqa.query.router import QueryRouter
from cookqa.retrieval.bm25 import BM25Retriever
from cookqa.retrieval.coordinator import RetrievalCoordinator
from cookqa.retrieval.faiss_store import FaissRetriever, FaissVectorIndex
from cookqa.retrieval.neo4j_store import Neo4jRetriever
from cookqa.service import SearchService


class UnavailableSearchService:
    def __init__(self, detail: str):
        self.detail = detail

    async def search(self, query: str):
        raise RuntimeError(self.detail)

    def get_recipe(self, recipe_id: str):
        return None


class RuntimeReadiness:
    def __init__(
        self,
        manifest: IndexManifest | None,
        bm25: BM25Retriever | None,
        vector_index: FaissVectorIndex | None,
        neo4j_driver: Any | None,
        ollama: OllamaClient,
        load_error: str | None = None,
    ) -> None:
        self.manifest = manifest
        self.bm25 = bm25
        self.vector_index = vector_index
        self.neo4j_driver = neo4j_driver
        self.ollama = ollama
        self.load_error = load_error

    def _graph_state(self) -> tuple[set[str], str | None]:
        if self.neo4j_driver is None or self.manifest is None:
            return set(), "Neo4j 未配置或不可用"
        records, _, _ = self.neo4j_driver.execute_query(
            "MATCH (recipe:Recipe {data_version: $data_version}) "
            "RETURN recipe.recipe_id AS recipe_id",
            data_version=self.manifest.data_version,
        )
        return {record["recipe_id"] for record in records}, None

    async def check(self) -> ReadinessReport:
        components: dict[str, ComponentStatus] = {}
        if self.load_error or not self.manifest or not self.bm25 or not self.vector_index:
            components["indexes"] = ComponentStatus(
                available=False, detail=self.load_error or "索引未加载"
            )
        else:
            try:
                graph_ids, graph_error = await asyncio.to_thread(self._graph_state)
                if graph_error:
                    raise ManifestMismatch(graph_error)
                validate_manifest(
                    self.manifest,
                    bm25_ids=set(self.bm25.recipe_ids),
                    faiss_ids=set(self.vector_index.recipe_ids),
                    graph_ids=graph_ids,
                    embedding_dimension=self.vector_index.dimension,
                )
                components["indexes"] = ComponentStatus(available=True)
                components["neo4j"] = ComponentStatus(available=True)
            except Exception as exc:
                components["indexes"] = ComponentStatus(available=False, detail=str(exc))
                components["neo4j"] = ComponentStatus(available=False, detail="Neo4j 校验失败")
        try:
            models = await self.ollama.available_models()
            required = {self.ollama.settings.chat_model, self.ollama.settings.embedding_model}
            missing = sorted(required - models)
            components["ollama"] = ComponentStatus(
                available=not missing,
                detail=("缺少模型: " + ", ".join(missing)) if missing else None,
            )
        except Exception:
            components["ollama"] = ComponentStatus(available=False, detail="Ollama 不可用")
        ready = bool(components) and all(item.available for item in components.values())
        return ReadinessReport(
            ready=ready,
            components=components,
            manifest=self.manifest.model_dump() if self.manifest else None,
        )


def _load_recipes(path: Path) -> dict[str, Recipe]:
    recipes: dict[str, Recipe] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            recipe = Recipe.model_validate_json(line)
            recipes[recipe.recipe_id] = recipe
    return recipes


def build_runtime(settings: Settings):
    ollama = OllamaClient(settings)
    try:
        active = json.loads(
            (settings.data_dir / "runtime" / "active.json").read_text(encoding="utf-8")
        )
        artifact_dir = settings.data_dir / "indexes" / active["version"]
        manifest = IndexManifest.load(artifact_dir / "index-manifest.json")
        recipes = _load_recipes(artifact_dir / "recipes.jsonl")
        bm25 = BM25Retriever.load(artifact_dir / "bm25.json")
        vector_index = FaissVectorIndex.load(
            artifact_dir / "faiss.index",
            artifact_dir / "faiss.ids.json",
        )

        driver = None
        if settings.neo4j_password:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
        retrievers = [bm25, FaissRetriever(vector_index, ollama, settings.dense_timeout_seconds)]
        if driver is not None:
            retrievers.append(Neo4jRetriever(driver))
        recipe_names: dict[str, str] = {}
        ingredient_names: set[str] = set()
        for recipe in recipes.values():
            recipe_names[recipe.name] = recipe.name
            recipe_names.update({alias: recipe.name for alias in recipe.aliases})
            ingredient_names.update(ingredient.name for ingredient in recipe.ingredients)
        router = QueryRouter(recipe_names, ingredient_names)
        service = SearchService(router, RetrievalCoordinator(recipes, retrievers), recipes)
        readiness = RuntimeReadiness(manifest, bm25, vector_index, driver, ollama)
        return service, readiness, ollama
    except Exception as exc:
        detail = f"运行数据未就绪: {exc.__class__.__name__}"
        return (
            UnavailableSearchService(detail),
            RuntimeReadiness(None, None, None, None, ollama, load_error=detail),
            ollama,
        )
