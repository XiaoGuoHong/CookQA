from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from collections.abc import Mapping, Sequence

from cookqa.models import QueryPlan, Recipe, SearchResult
from cookqa.retrieval.fusion import reciprocal_rank_fusion, satisfies_hard_filters
from cookqa.retrieval.ports import RankedRetriever


class RetrievalUnavailable(RuntimeError):
    pass


@dataclass(slots=True)
class RetrievalOutcome:
    results: list[SearchResult]
    strategy: list[str]
    timings_ms: dict[str, float]
    unavailable_components: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    constraints_verified: bool = True


class RetrievalCoordinator:
    def __init__(
        self,
        recipes: Mapping[str, Recipe],
        retrievers: Sequence[RankedRetriever],
        weights: Mapping[str, float] | None = None,
    ) -> None:
        self.recipes = dict(recipes)
        self.retrievers = {retriever.name: retriever for retriever in retrievers}
        self.weights = dict(weights or {"bm25": 1.0, "faiss": 1.0, "neo4j": 1.0})

    async def _run(self, retriever: RankedRetriever, plan: QueryPlan, limit: int):
        started = time.perf_counter()
        candidates = await retriever.search(plan, limit)
        return candidates, (time.perf_counter() - started) * 1000

    async def search(self, plan: QueryPlan, limit: int = 5) -> RetrievalOutcome:
        selected = [
            self.retrievers[name]
            for name in plan.retrieval_strategy
            if name in self.retrievers and name != "exact"
        ]
        if plan.intent == "exact_recipe" and plan.recognized_recipes:
            exact_ids = [
                recipe.recipe_id
                for recipe in self.recipes.values()
                if recipe.name in plan.recognized_recipes
                or set(recipe.aliases).intersection(plan.recognized_recipes)
            ]
            results = [
                SearchResult(recipe=self.recipes[recipe_id], score=1.0, reasons=["菜名精确匹配"], retrieval_sources=["exact"])
                for recipe_id in exact_ids[:limit]
            ]
            return RetrievalOutcome(results=results, strategy=["exact"], timings_ms={"exact": 0.0})
        if not selected:
            raise RetrievalUnavailable("没有可用的检索组件")

        raw_results = await asyncio.gather(
            *(self._run(retriever, plan, max(limit * 4, 20)) for retriever in selected),
            return_exceptions=True,
        )
        rankings: dict[str, list[str]] = {}
        reasons_by_id: dict[str, list[str]] = {}
        timings: dict[str, float] = {}
        unavailable: list[str] = []
        for retriever, result in zip(selected, raw_results, strict=True):
            if isinstance(result, BaseException):
                unavailable.append(retriever.name)
                continue
            candidates, elapsed = result
            timings[retriever.name] = elapsed
            rankings[retriever.name] = [candidate.recipe_id for candidate in candidates]
            for candidate in candidates:
                reasons_by_id.setdefault(candidate.recipe_id, []).extend(candidate.reasons)

        if not rankings:
            raise RetrievalUnavailable("所有检索组件均不可用")

        graph_required = plan.constraints.has_hard_filters() or bool(
            plan.required_ingredients or plan.excluded_ingredients
        )
        graph_failed = graph_required and "neo4j" in unavailable
        warnings: list[str] = []
        if graph_failed:
            warnings.append("Neo4j 不可用，明确条件未经过图数据库验证。")

        fused = reciprocal_rank_fusion(rankings, self.weights)
        results: list[SearchResult] = []
        for candidate in fused:
            recipe = self.recipes.get(candidate.recipe_id)
            if recipe is None:
                continue
            if not graph_failed and not satisfies_hard_filters(
                recipe,
                plan.required_ingredients,
                plan.excluded_ingredients,
                plan.constraints,
            ):
                continue
            results.append(
                SearchResult(
                    recipe=recipe,
                    score=candidate.score,
                    reasons=list(dict.fromkeys(reasons_by_id.get(candidate.recipe_id, []))),
                    retrieval_sources=candidate.sources,
                    constraints_verified=not graph_failed,
                )
            )
            if len(results) == limit:
                break

        return RetrievalOutcome(
            results=results,
            strategy=list(rankings),
            timings_ms=timings,
            unavailable_components=unavailable,
            warnings=warnings,
            constraints_verified=not graph_failed,
        )
