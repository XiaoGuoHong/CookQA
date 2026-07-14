from __future__ import annotations

from collections.abc import Mapping

from cookqa.comparison import RecipeComparator
from cookqa.models import DegradationStatus, Recipe, SearchResponse, SearchResult
from cookqa.query.router import QueryRouter
from cookqa.retrieval.coordinator import RetrievalCoordinator, RetrievalUnavailable


class SearchService:
    def __init__(
        self,
        router: QueryRouter,
        coordinator: RetrievalCoordinator,
        recipes: Mapping[str, Recipe],
    ) -> None:
        self.router = router
        self.coordinator = coordinator
        self.recipes = dict(recipes)
        self._recipes_by_name: dict[str, Recipe] = {}
        for recipe in self.recipes.values():
            self._recipes_by_name[recipe.name] = recipe
            for alias in recipe.aliases:
                self._recipes_by_name[alias] = recipe

    def _comparison_response(self, plan) -> SearchResponse:
        targets = [
            self._recipes_by_name.get(name)
            for name in plan.recognized_recipes
        ]
        if len(targets) != 2 or any(recipe is None for recipe in targets):
            raise RetrievalUnavailable("无法定位要比较的两道菜")
        left, right = targets
        return SearchResponse(
            query_plan=plan,
            results=[
                SearchResult(
                    recipe=left,
                    score=1.0,
                    reasons=["菜谱比较目标"],
                    retrieval_sources=["comparison"],
                ),
                SearchResult(
                    recipe=right,
                    score=1.0,
                    reasons=["菜谱比较目标"],
                    retrieval_sources=["comparison"],
                ),
            ],
            comparison=RecipeComparator.compare(left, right),
            retrieval_strategy=["comparison"],
        )

    async def search(self, query: str) -> SearchResponse:
        plan = self.router.route(query)
        if plan.intent == "clarification_required":
            return SearchResponse(
                query_plan=plan,
                retrieval_strategy=[],
                degradation=DegradationStatus(
                    warnings=[plan.clarification] if plan.clarification else []
                ),
            )
        if plan.intent == "recipe_comparison":
            return self._comparison_response(plan)
        outcome = await self.coordinator.search(plan, limit=5)
        return SearchResponse(
            query_plan=plan,
            results=outcome.results,
            retrieval_strategy=outcome.strategy,
            timings_ms=outcome.timings_ms,
            degradation=DegradationStatus(
                degraded=bool(outcome.unavailable_components),
                unavailable_components=outcome.unavailable_components,
                warnings=outcome.warnings,
            ),
        )

    def get_recipe(self, recipe_id: str) -> Recipe | None:
        return self.recipes.get(recipe_id)
