import asyncio

from cookqa.models import Ingredient, QueryPlan, RankedCandidate, Recipe
from cookqa.retrieval.coordinator import RetrievalCoordinator


class FakeRetriever:
    def __init__(self, name, recipe_ids):
        self.name = name
        self.recipe_ids = recipe_ids

    async def search(self, plan, limit):
        return [
            RankedCandidate(recipe_id=recipe_id, score=1.0, source=self.name)
            for recipe_id in self.recipe_ids[:limit]
        ]


def make_recipe(recipe_id, name):
    return Recipe(
        recipe_id=recipe_id,
        name=name,
        ingredients=[Ingredient(name="salt", raw="salt")],
        source_path=f"dishes/{recipe_id}.md",
        source_version="abc",
    )


def test_similar_recipe_preserves_faiss_similarity_order_over_generic_graph_rank():
    ids = ["source", "desired-1", "desired-2", "common-1", "common-2", "common-3"]
    recipes = {recipe_id: make_recipe(recipe_id, recipe_id) for recipe_id in ids}
    coordinator = RetrievalCoordinator(
        recipes,
        [
            FakeRetriever(
                "faiss",
                ["source", "desired-1", "desired-2", "common-1", "common-2", "common-3"],
            ),
            FakeRetriever(
                "neo4j",
                ["common-1", "common-2", "common-3", "desired-2", "desired-1"],
            ),
        ],
    )
    plan = QueryPlan(
        original_query="find recipes similar to source",
        normalized_query="find recipes similar to source",
        intent="similar_recipe",
        recognized_recipes=["source"],
        retrieval_strategy=["faiss", "neo4j"],
        confidence=0.95,
    )

    outcome = asyncio.run(coordinator.search(plan))

    assert [result.recipe.recipe_id for result in outcome.results[:2]] == [
        "desired-1",
        "desired-2",
    ]
