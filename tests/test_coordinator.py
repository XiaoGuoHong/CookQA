import asyncio

from cookqa.models import Ingredient, QueryConstraints, QueryPlan, RankedCandidate, Recipe
from cookqa.retrieval.coordinator import RetrievalCoordinator


class FakeRetriever:
    def __init__(self, name, ids=None, error=None):
        self.name = name
        self._ids = ids or []
        self._error = error

    async def search(self, plan, limit):
        if self._error:
            raise self._error
        return [
            RankedCandidate(recipe_id=recipe_id, score=1.0, source=self.name)
            for recipe_id in self._ids[:limit]
        ]


def make_recipe(recipe_id="r1", duration=15):
    return Recipe(
        recipe_id=recipe_id,
        name="番茄炒蛋",
        ingredients=[Ingredient(name="番茄", raw="番茄"), Ingredient(name="鸡蛋", raw="鸡蛋")],
        duration_minutes=duration,
        source_path="dishes/tomato.md",
        source_version="abc",
    )


def test_graph_failure_with_hard_filter_marks_results_unverified():
    coordinator = RetrievalCoordinator(
        recipes={"r1": make_recipe()},
        retrievers=[
            FakeRetriever("bm25", ["r1"]),
            FakeRetriever("faiss", ["r1"]),
            FakeRetriever("neo4j", error=RuntimeError("offline")),
        ],
    )
    plan = QueryPlan(
        original_query="20分钟内的菜",
        normalized_query="20分钟内的菜",
        intent="conditional_recommendation",
        constraints=QueryConstraints(max_minutes=20),
        retrieval_strategy=["bm25", "faiss", "neo4j"],
        confidence=0.9,
    )

    outcome = asyncio.run(coordinator.search(plan))

    assert "neo4j" in outcome.unavailable_components
    assert outcome.constraints_verified is False
    assert outcome.warnings


def test_all_retrievers_failed_raises_service_error():
    coordinator = RetrievalCoordinator(
        recipes={"r1": make_recipe()},
        retrievers=[FakeRetriever("bm25", error=RuntimeError("offline"))],
    )
    plan = QueryPlan(
        original_query="家常菜",
        normalized_query="家常菜",
        intent="semantic_recommendation",
        retrieval_strategy=["bm25"],
        confidence=0.5,
    )

    try:
        asyncio.run(coordinator.search(plan))
    except Exception as exc:
        assert exc.__class__.__name__ == "RetrievalUnavailable"
    else:
        raise AssertionError("expected RetrievalUnavailable")
