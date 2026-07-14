from cookqa.comparison import RecipeComparator
from cookqa.models import Ingredient, Recipe


def make_recipe(
    recipe_id,
    name,
    ingredient_names,
    *,
    categories=None,
    methods=None,
    tools=None,
    difficulty=None,
    duration_minutes=None,
):
    return Recipe(
        recipe_id=recipe_id,
        name=name,
        ingredients=[
            Ingredient(name=ingredient, raw=ingredient)
            for ingredient in ingredient_names
        ],
        categories=categories or [],
        methods=methods or [],
        tools=tools or [],
        difficulty=difficulty,
        duration_minutes=duration_minutes,
        source_path=f"dishes/{recipe_id}.md",
        source_version="abc",
    )


def test_comparator_returns_deterministic_structured_differences():
    kung_pao = make_recipe(
        "r1",
        "宫保鸡丁",
        ["鸡肉", "花生"],
        categories=["家常菜", "川菜"],
        methods=["炒"],
        tools=["炒锅"],
        difficulty="简单",
        duration_minutes=20,
    )
    laziji = make_recipe(
        "r2",
        "辣子鸡",
        ["鸡肉", "干辣椒"],
        categories=["川菜"],
        methods=["炸"],
        tools=["炒锅"],
        difficulty="困难",
        duration_minutes=35,
    )

    comparison = RecipeComparator.compare(kung_pao, laziji)

    assert comparison.left_recipe_id == "r1"
    assert comparison.right_recipe_id == "r2"
    assert comparison.ingredients.common == ["鸡肉"]
    assert comparison.ingredients.only_left == ["花生"]
    assert comparison.ingredients.only_right == ["干辣椒"]
    assert comparison.categories.common == ["川菜"]
    assert comparison.categories.only_left == ["家常菜"]
    assert comparison.methods.only_left == ["炒"]
    assert comparison.methods.only_right == ["炸"]
    assert comparison.tools.common == ["炒锅"]
    assert comparison.difficulty.relationship == "different"
    assert comparison.duration_minutes.left == 20
    assert comparison.duration_minutes.right == 35
    assert comparison.duration_minutes.relationship == "different"


def test_missing_fields_are_unknown_instead_of_inferred():
    left = make_recipe(
        "r1",
        "宫保鸡丁",
        ["鸡肉"],
        categories=["川菜"],
        methods=["炒"],
        tools=["炒锅"],
        difficulty="简单",
        duration_minutes=20,
    )
    right = make_recipe("r2", "辣子鸡", ["鸡肉"])

    comparison = RecipeComparator.compare(left, right)

    assert comparison.categories.common == "无法确认"
    assert comparison.categories.only_left == "无法确认"
    assert comparison.methods.only_right == "无法确认"
    assert comparison.tools.left == "无法确认"
    assert comparison.difficulty.right == "无法确认"
    assert comparison.difficulty.relationship == "unknown"
    assert comparison.duration_minutes.right == "无法确认"
    assert comparison.duration_minutes.relationship == "unknown"


def test_equal_known_scalar_is_marked_same():
    left = make_recipe("r1", "菜一", ["鸡蛋"], difficulty="简单")
    right = make_recipe("r2", "菜二", ["番茄"], difficulty="简单")

    comparison = RecipeComparator.compare(left, right)

    assert comparison.difficulty.relationship == "same"
