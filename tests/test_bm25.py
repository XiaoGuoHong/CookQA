import asyncio

from cookqa.models import Ingredient, QueryPlan, Recipe
from cookqa.retrieval.bm25 import BM25Retriever


def make_recipe(recipe_id, name, ingredients):
    return Recipe(
        recipe_id=recipe_id,
        name=name,
        ingredients=[Ingredient(name=item, raw=item) for item in ingredients],
        source_path=f"dishes/{name}.md",
        source_version="abc",
    )


def test_bm25_ranks_exact_dish_name_first(tmp_path):
    retriever = BM25Retriever.build(
        [
            make_recipe("tomato", "番茄炒蛋", ["番茄", "鸡蛋"]),
            make_recipe("chicken", "宫保鸡丁", ["鸡肉", "花生"]),
        ]
    )
    plan = QueryPlan(
        original_query="宫保鸡丁",
        normalized_query="宫保鸡丁",
        intent="exact_recipe",
        retrieval_strategy=["bm25"],
        confidence=1,
    )

    result = asyncio.run(retriever.search(plan, limit=2))

    assert result[0].recipe_id == "chicken"


def test_bm25_round_trips_through_disk(tmp_path):
    path = tmp_path / "bm25.json"
    original = BM25Retriever.build([make_recipe("r1", "番茄炒蛋", ["番茄", "鸡蛋"])])
    original.save(path)

    loaded = BM25Retriever.load(path)

    assert loaded.recipe_ids == ["r1"]
