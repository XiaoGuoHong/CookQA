from cookqa.models import QueryConstraints, QueryPlan
from cookqa.retrieval.neo4j_store import build_candidate_query


def test_neo4j_query_uses_parameters_for_user_values():
    plan = QueryPlan(
        original_query="不含猪肉的菜",
        normalized_query="不含猪肉的菜",
        intent="conditional_recommendation",
        excluded_ingredients=["猪肉"],
        constraints=QueryConstraints(max_minutes=20),
        retrieval_strategy=["neo4j"],
        confidence=0.9,
    )

    cypher, parameters = build_candidate_query(plan, limit=5, data_version="v2")

    assert "猪肉" not in cypher
    assert "$excluded_ingredients" in cypher
    assert "$max_minutes" in cypher
    assert parameters["excluded_ingredients"] == ["猪肉"]
    assert parameters["data_version"] == "v2"
    assert parameters["max_minutes"] == 20
