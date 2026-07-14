import asyncio

import pytest

from cookqa.models import Ingredient, QueryPlan, Recipe
from cookqa.query.router import QueryRouter
from cookqa.retrieval.coordinator import RetrievalUnavailable
from cookqa.service import SearchService


class ComparisonRouter:
    def route(self, query):
        return QueryPlan(
            original_query=query,
            normalized_query=query,
            intent="recipe_comparison",
            recognized_recipes=["宫保鸡丁", "辣子鸡"],
            retrieval_strategy=["neo4j"],
            confidence=0.98,
        )


class MissingRecipeRouter:
    def route(self, query):
        return QueryPlan(
            original_query=query,
            normalized_query=query,
            intent="recipe_comparison",
            recognized_recipes=["宫保鸡丁", "不存在的菜"],
            retrieval_strategy=["neo4j"],
            confidence=0.98,
        )


class ForbiddenCoordinator:
    async def search(self, plan, limit=5):
        raise AssertionError("comparison must not call ranked retrieval")


def recipe(recipe_id, name, ingredients):
    return Recipe(
        recipe_id=recipe_id,
        name=name,
        ingredients=[Ingredient(name=item, raw=item) for item in ingredients],
        source_path=f"dishes/{recipe_id}.md",
        source_version="abc",
    )


def test_comparison_returns_exactly_two_targets_without_ranked_retrieval():
    recipes = {
        "r1": recipe("r1", "宫保鸡丁", ["鸡肉", "花生"]),
        "r2": recipe("r2", "辣子鸡", ["鸡肉", "干辣椒"]),
        "r3": recipe("r3", "鱼香肉丝", ["猪肉"]),
    }
    service = SearchService(ComparisonRouter(), ForbiddenCoordinator(), recipes)

    response = asyncio.run(service.search("宫保鸡丁和辣子鸡有什么区别"))

    assert [item.recipe.name for item in response.results] == ["宫保鸡丁", "辣子鸡"]
    assert response.retrieval_strategy == ["comparison"]
    assert response.comparison.ingredients.common == ["鸡肉"]


def test_comparison_rejects_unresolved_recipe_target():
    recipes = {"r1": recipe("r1", "宫保鸡丁", ["鸡肉"])}
    service = SearchService(MissingRecipeRouter(), ForbiddenCoordinator(), recipes)

    with pytest.raises(RetrievalUnavailable, match="无法定位要比较的两道菜"):
        asyncio.run(service.search("宫保鸡丁和不存在的菜有什么区别"))


def test_router_requires_exactly_two_comparison_targets():
    router = QueryRouter(
        {
            "宫保鸡丁": "宫保鸡丁",
            "辣子鸡": "辣子鸡",
            "鱼香肉丝": "鱼香肉丝",
        },
        set(),
    )

    plan = router.route("宫保鸡丁、辣子鸡和鱼香肉丝哪个好")

    assert plan.intent == "clarification_required"
    assert plan.retrieval_strategy == []
    assert plan.clarification == "一次只能比较两道菜，请保留两个菜名。"
