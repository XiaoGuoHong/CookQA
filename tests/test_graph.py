from pathlib import Path

from cookqa.graph import RecipeGraph
from cookqa.parser import load_recipes


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "howtocook"


def test_graph_indexes_ingredients_and_categories():
    recipes = load_recipes(FIXTURE_ROOT)
    graph = RecipeGraph.build(recipes)

    matches = graph.recipe_matches("牛肉可以怎么做")

    assert "dishes/meat_dish/水煮牛肉/水煮牛肉.md" in matches
    assert "ingredient:牛肉" in matches["dishes/meat_dish/水煮牛肉/水煮牛肉.md"]


def test_graph_matches_exact_dish_name():
    recipes = load_recipes(FIXTURE_ROOT)
    graph = RecipeGraph.build(recipes)

    matches = graph.recipe_matches("番茄炒蛋怎么做")

    assert "dishes/vegetable_dish/西红柿炒鸡蛋.md" in matches
