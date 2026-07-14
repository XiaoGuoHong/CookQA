from cookqa.models import QueryPlan
from cookqa.retrieval.neo4j_store import Neo4jRetriever, build_candidate_query


class RecordingDriver:
    def __init__(self):
        self.parameters = None

    def execute_query(self, cypher, **parameters):
        self.parameters = parameters
        return ([], None, None)


def plan():
    return QueryPlan(
        original_query="家常菜",
        normalized_query="家常菜",
        intent="semantic_recommendation",
        retrieval_strategy=["neo4j"],
        confidence=0.5,
    )


def test_candidate_query_requires_data_version():
    cypher, parameters = build_candidate_query(plan(), limit=5, data_version="v2")

    assert "recipe.data_version = $data_version" in cypher
    assert parameters["data_version"] == "v2"


def test_retriever_passes_its_version_to_the_query():
    driver = RecordingDriver()
    retriever = Neo4jRetriever(driver, "v2")

    retriever._search_sync(plan(), 5)

    assert driver.parameters["parameters_"]["data_version"] == "v2"
