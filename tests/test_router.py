import pytest

from cookqa.query.router import QueryRouter


@pytest.fixture
def router():
    return QueryRouter(
        recipe_names={
            "宫保鸡丁": "宫保鸡丁",
            "辣子鸡": "辣子鸡",
            "鱼香肉丝": "鱼香肉丝",
        },
        ingredient_names={"鸡蛋", "番茄", "鸡肉", "猪肉"},
        ingredient_aliases={"西红柿": "番茄"},
    )


@pytest.mark.parametrize(
    ("query", "intent"),
    [
        ("宫保鸡丁怎么做", "exact_recipe"),
        ("鸡蛋和番茄能做什么", "ingredient_lookup"),
        ("推荐20分钟内不辣的鸡肉菜", "conditional_recommendation"),
        ("想吃清淡又下饭的菜", "semantic_recommendation"),
        ("找和鱼香肉丝相似但不含猪肉的菜", "similar_recipe"),
        ("宫保鸡丁和辣子鸡有什么区别", "recipe_comparison"),
    ],
)
def test_routes_supported_intents(router, query, intent):
    assert router.route(query).intent == intent


def test_step_question_without_recipe_requests_clarification(router):
    plan = router.route("鸡蛋什么时候下锅")

    assert plan.intent == "clarification_required"
    assert "菜名" in plan.clarification


def test_conditional_query_extracts_hard_constraints(router):
    plan = router.route("推荐20分钟内不辣的鸡肉菜")

    assert plan.constraints.max_minutes == 20
    assert plan.required_ingredients == ["鸡肉"]
    assert "辣" in plan.excluded_ingredients


def test_alias_is_normalized_to_canonical_ingredient(router):
    plan = router.route("西红柿和鸡蛋能做什么")

    assert plan.required_ingredients == ["番茄", "鸡蛋"]


def test_blank_query_is_rejected(router):
    with pytest.raises(ValueError, match="不能为空"):
        router.route("   ")
