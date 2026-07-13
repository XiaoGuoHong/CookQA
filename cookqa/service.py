from __future__ import annotations

from collections.abc import Mapping

from cookqa.models import DegradationStatus, Recipe, SearchResponse
from cookqa.query.router import QueryRouter
from cookqa.retrieval.coordinator import RetrievalCoordinator


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
