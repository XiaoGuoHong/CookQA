from pathlib import Path

from cookqa.graph import RecipeGraph
from cookqa.parser import load_recipes
from cookqa.retrieval import RecipeRetriever


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "howtocook"


def build_retriever():
    recipes = load_recipes(FIXTURE_ROOT)
    graph = RecipeGraph.build(recipes)
    return RecipeRetriever(
        recipes=recipes,
        graph=graph,
        recipe_index=None,
        step_index=None,
        embed_query=None,
    )


def test_ingredient_question_returns_multiple_recommendations():
    mode, recommendations = build_retriever().search("牛肉可以怎么做", top_k=5)

    assert mode == "ingredient_exploration"
    assert recommendations[0].name == "水煮牛肉"
    assert "牛肉" in recommendations[0].match_reason


def test_alias_dish_question_finds_tomato_egg():
    mode, recommendations = build_retriever().search("番茄炒蛋怎么做", top_k=3)

    assert mode == "dish_lookup"
    assert recommendations[0].name == "西红柿炒鸡蛋"


def test_missing_question_marks_no_exact_match():
    mode, recommendations = build_retriever().search("黯然销魂饭怎么做", top_k=3)

    assert mode == "missing_or_fictional"
    assert recommendations == []
