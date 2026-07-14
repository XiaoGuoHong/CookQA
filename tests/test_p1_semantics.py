from cookqa.models import Ingredient, QueryConstraints, Recipe
from cookqa.query.router import QueryRouter
from cookqa.retrieval.fusion import satisfies_hard_filters


def test_not_spicy_is_a_structured_label_not_an_ingredient():
    router = QueryRouter(
        recipe_names={},
        ingredient_names={"虾肉"},
    )

    plan = router.route("推荐不辣的虾菜")

    assert "辣" not in plan.excluded_ingredients
    assert plan.constraints.excluded_labels == ["spicy"]


def test_spicy_request_is_a_structured_label_not_an_ingredient():
    router = QueryRouter(recipe_names={}, ingredient_names={"虾肉"})

    plan = router.route("推荐辣味的虾菜")

    assert "辣" not in plan.required_ingredients
    assert plan.constraints.required_labels == ["spicy"]


def _recipe(*ingredient_names: str) -> Recipe:
    return Recipe(
        recipe_id="r1",
        name="测试菜",
        ingredients=[Ingredient(name=name, raw=name) for name in ingredient_names],
        source_path="dishes/test.md",
        source_version="abc",
    )


def test_excluded_spicy_label_rejects_chili_recipe():
    assert not satisfies_hard_filters(
        _recipe("辣椒"), [], [], QueryConstraints(excluded_labels=["spicy"])
    )


def test_required_spicy_label_rejects_recipe_without_spicy_evidence():
    assert not satisfies_hard_filters(
        _recipe("鸡蛋"), [], [], QueryConstraints(required_labels=["spicy"])
    )
