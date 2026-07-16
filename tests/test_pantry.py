from cookqa.models import Ingredient, Recipe
from cookqa.pantry import PantryMatcher


def recipe(name, ingredients, *, duration=20, tags=None):
    return Recipe(
        recipe_id=name,
        name=name,
        ingredients=[
            Ingredient(name=item, raw=item, optional=item.startswith("可选"))
            for item in ingredients
        ],
        duration_minutes=duration,
        tags=tags or [],
        steps=["完成"],
        source_path=f"{name}.md",
        source_version="test",
    )


def matcher(recipes):
    return PantryMatcher(
        recipes.values(),
        {"西红柿": "番茄", "蕃茄": "番茄"},
        staples={"盐", "食用油"},
    )


def test_aliases_are_deduplicated_and_staples_are_not_missing():
    recipes = {"r": recipe("番茄炒蛋", ["番茄", "鸡蛋", "盐"])}

    result = matcher(recipes).match([" 西红柿 ", "番茄", "鸡蛋"], [])

    assert result.normalized_existing == ["番茄", "鸡蛋"]
    assert result.ready[0].available_ingredients == ["番茄", "鸡蛋", "盐"]
    assert result.ready[0].missing_ingredients == []
    assert result.ready[0].staple_ingredients == ["盐"]


def test_optional_ingredients_do_not_count_as_missing():
    recipes = {"r": recipe("炒蛋", ["鸡蛋", "可选葱"])}

    result = matcher(recipes).match(["鸡蛋"], [], use_staples=False)

    assert [item.recipe.name for item in result.ready] == ["炒蛋"]
    assert result.ready[0].optional_ingredients == ["可选葱"]


def test_exclusion_time_and_no_spicy_are_hard_filters():
    recipes = {
        "ok": recipe("番茄蛋", ["番茄", "鸡蛋"], duration=15),
        "slow": recipe("慢炖蛋", ["番茄", "鸡蛋"], duration=40),
        "spicy": recipe("辣蛋", ["番茄", "辣椒"], duration=15, tags=["辣"]),
    }

    result = matcher(recipes).match(
        ["番茄", "鸡蛋"], ["辣椒"], max_minutes=20, no_spicy=True, use_staples=False
    )

    assert [item.recipe.name for item in result.ready] == ["番茄蛋"]
    assert all(
        item.recipe.name not in {"慢炖蛋", "辣蛋"}
        for group in (result.ready, result.near, result.related)
        for item in group
    )


def test_groups_have_boundaries_limits_and_stable_sorting():
    recipes = {
        f"r{i}": recipe(
            f"菜{i}", ["番茄", *(["鸡蛋"] if i < 7 else ["鸡蛋", "猪肉", "葱"])], duration=10
        )
        for i in range(8)
    }

    result = matcher(recipes).match(["番茄", "鸡蛋"], [], use_staples=False)

    assert len(result.ready) == 5
    assert all(len(item.missing_ingredients) <= 2 for item in result.near)
    assert all(len(item.missing_ingredients) > 2 for item in result.related)
    assert result.ready[0].coverage == 1.0
    assert [item.recipe.name for item in result.ready] == sorted(
        item.recipe.name for item in result.ready
    )
