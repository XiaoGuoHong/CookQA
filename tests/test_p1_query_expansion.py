from cookqa.query.router import QueryRouter


def test_cold_dish_query_expands_to_common_recipe_name_term():
    router = QueryRouter(recipe_names={}, ingredient_names=set())

    plan = router.route("\u63a8\u8350\u4e00\u9053\u51c9\u83dc")

    assert plan.normalized_query.endswith(" \u51c9\u62cc")
    assert plan.constraints.categories == ["vegetable_dish"]
