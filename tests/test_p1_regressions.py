import asyncio

from cookqa.models import Ingredient, QueryPlan, RankedCandidate, Recipe
from cookqa.query.router import QueryRouter
from cookqa.retrieval.coordinator import RetrievalCoordinator


def test_not_using_ingredient_is_an_exclusion():
    router = QueryRouter(recipe_names={}, ingredient_names={"猪肉"})

    plan = router.route("推荐不用猪肉的鱼菜")

    assert plan.required_ingredients == []
    assert plan.excluded_ingredients == ["猪肉"]


def test_similar_recipe_name_ingredients_are_not_hard_requirements():
    router = QueryRouter(
        recipe_names={"辣椒炒肉的做法": "辣椒炒肉的做法"},
        ingredient_names={"辣椒", "猪肉"},
    )

    plan = router.route("找和辣椒炒肉相似但不含猪肉的菜")

    assert plan.intent == "similar_recipe"
    assert plan.required_ingredients == []
    assert plan.excluded_ingredients == ["猪肉"]


def test_simple_breakfast_does_not_require_missing_difficulty_metadata():
    router = QueryRouter(recipe_names={}, ingredient_names=set())

    plan = router.route("来一道简单的早餐")

    assert plan.constraints.difficulties == []
    assert plan.constraints.categories == ["breakfast"]


def test_runtime_aliases_cover_generic_evaluation_ingredients():
    router = QueryRouter(
        recipe_names={},
        ingredient_names={"虾仁", "红薯粉条"},
        ingredient_aliases={"虾": "虾", "粉条": "粉条"},
    )

    shrimp = router.route("虾和黄油能做什么")
    noodles = router.route("猪肉和粉条能做什么")

    assert "虾" in shrimp.required_ingredients
    assert "粉条" in noodles.required_ingredients


class _Retriever:
    name = "bm25"

    def __init__(self, recipe_ids):
        self.recipe_ids = recipe_ids

    async def search(self, plan, limit):
        return [
            RankedCandidate(recipe_id=recipe_id, score=1.0, source=self.name)
            for recipe_id in self.recipe_ids[:limit]
        ]


def _recipe(recipe_id, name):
    return Recipe(
        recipe_id=recipe_id,
        name=name,
        ingredients=[Ingredient(name="盐", raw="盐")],
        source_path=f"dishes/{recipe_id}.md",
        source_version="abc",
    )


def test_conditional_recommendation_keeps_retrieval_rank_ahead_of_fallback_text_score():
    recipes = {
        "desired": _recipe("desired", "清蒸鲈鱼"),
        "fallback": _recipe("fallback", "推荐鱼菜"),
    }
    coordinator = RetrievalCoordinator(recipes, [_Retriever(["desired", "fallback"])])
    plan = QueryPlan(
        original_query="推荐鱼菜",
        normalized_query="推荐鱼菜",
        intent="conditional_recommendation",
        retrieval_strategy=["bm25"],
        confidence=0.9,
    )

    outcome = asyncio.run(coordinator.search(plan))

    assert [item.recipe.recipe_id for item in outcome.results] == ["desired", "fallback"]


def test_similar_recipe_does_not_return_the_reference_recipe():
    recipes = {
        "source": _recipe("source", "凉拌黄瓜的做法"),
        "similar": _recipe("similar", "凉拌莴笋的做法"),
    }
    coordinator = RetrievalCoordinator(recipes, [_Retriever(["source", "similar"])])
    plan = QueryPlan(
        original_query="找和凉拌黄瓜类似的菜",
        normalized_query="找和凉拌黄瓜类似的菜",
        intent="similar_recipe",
        recognized_recipes=["凉拌黄瓜的做法"],
        retrieval_strategy=["bm25"],
        confidence=0.95,
    )

    outcome = asyncio.run(coordinator.search(plan))

    assert [item.recipe.recipe_id for item in outcome.results] == ["similar"]
