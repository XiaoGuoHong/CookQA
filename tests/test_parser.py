from pathlib import Path

from cookqa.parser import load_recipes, parse_recipe_file


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "howtocook"


def test_parse_recipe_file_extracts_structured_fields():
    recipe_path = FIXTURE_ROOT / "dishes" / "vegetable_dish" / "西红柿炒鸡蛋.md"

    recipe = parse_recipe_file(recipe_path, FIXTURE_ROOT)

    assert recipe.recipe_id == "dishes/vegetable_dish/西红柿炒鸡蛋.md"
    assert recipe.name == "西红柿炒鸡蛋"
    assert recipe.category == "素菜"
    assert recipe.description == "酸甜开胃的家常菜。"
    assert recipe.difficulty == "★★"
    assert recipe.calories == "252 大卡"
    assert recipe.ingredients == ["西红柿", "鸡蛋", "食用油", "盐"]
    assert recipe.steps[0] == "西红柿洗净切块。"
    assert recipe.notes == ["可以加葱花。"]


def test_load_recipes_walks_dishes_only():
    recipes = load_recipes(FIXTURE_ROOT)

    names = sorted(recipe.name for recipe in recipes)
    assert names == ["水煮牛肉", "西红柿炒鸡蛋"]
