import asyncio

from cookqa.models import Ingredient, QueryPlan, Recipe, SearchResult
from cookqa.retrieval.coordinator import RetrievalOutcome
from cookqa.service import SearchService


class FakeRouter:
    def route(self, query):
        return QueryPlan(
            original_query=query,
            normalized_query=query,
            intent="semantic_recommendation",
            retrieval_strategy=["bm25"],
            confidence=0.5,
        )


class FakeCoordinator:
    async def search(self, plan, limit=5):
        recipe = Recipe(
            recipe_id="r1",
            name="番茄炒蛋",
            ingredients=[Ingredient(name="番茄", raw="番茄")],
            source_path="dishes/tomato.md",
            source_version="abc",
        )
        return RetrievalOutcome(
            results=[SearchResult(recipe=recipe, score=1, retrieval_sources=["bm25"])],
            strategy=["bm25"],
            timings_ms={"bm25": 1.5},
        )


def test_search_service_returns_structured_response():
    service = SearchService(FakeRouter(), FakeCoordinator(), recipes={})

    response = asyncio.run(service.search("家常菜"))

    assert response.results[0].recipe.name == "番茄炒蛋"
    assert response.retrieval_strategy == ["bm25"]
    assert response.timings_ms["bm25"] == 1.5
