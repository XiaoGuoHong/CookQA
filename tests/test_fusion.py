from cookqa.models import Ingredient, QueryConstraints, Recipe
from cookqa.retrieval.fusion import reciprocal_rank_fusion, satisfies_hard_filters


def recipe(**overrides):
    values = {
        "recipe_id": "r1",
        "name": "测试菜",
        "ingredients": [Ingredient(name="鸡蛋", raw="鸡蛋 2 个")],
        "source_path": "dishes/test.md",
        "source_version": "abc",
    }
    values.update(overrides)
    return Recipe(**values)


def test_rrf_fuses_by_rank_not_raw_score():
    fused = reciprocal_rank_fusion(
        {"bm25": ["a", "b"], "faiss": ["b", "a"], "neo4j": ["b"]},
        weights={"bm25": 1.0, "faiss": 1.0, "neo4j": 1.0},
    )

    assert fused[0].recipe_id == "b"
    assert fused[0].sources == ["bm25", "faiss", "neo4j"]


def test_missing_duration_does_not_pass_max_duration_filter():
    assert not satisfies_hard_filters(
        recipe(duration_minutes=None),
        required_ingredients=[],
        excluded_ingredients=[],
        constraints=QueryConstraints(max_minutes=20),
    )


def test_excluded_ingredient_is_removed():
    assert not satisfies_hard_filters(
        recipe(),
        required_ingredients=[],
        excluded_ingredients=["鸡蛋"],
        constraints=QueryConstraints(),
    )
