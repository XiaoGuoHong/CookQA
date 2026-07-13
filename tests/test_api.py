from fastapi.testclient import TestClient

from api.app import create_app
from cookqa.models import (
    ComponentStatus,
    DegradationStatus,
    Ingredient,
    QueryPlan,
    ReadinessReport,
    Recipe,
    SearchResponse,
)


class FakeService:
    def __init__(self):
        self.recipe = Recipe(
            recipe_id="r1",
            name="番茄炒蛋",
            ingredients=[Ingredient(name="番茄", raw="番茄")],
            steps=["炒熟"],
            source_path="dishes/tomato.md",
            source_version="abc",
        )

    async def search(self, query):
        return SearchResponse(
            query_plan=QueryPlan(
                original_query=query,
                normalized_query=query,
                intent="semantic_recommendation",
                retrieval_strategy=["bm25"],
                confidence=0.5,
            ),
            retrieval_strategy=["bm25"],
            degradation=DegradationStatus(),
        )

    def get_recipe(self, recipe_id):
        return self.recipe if recipe_id == "r1" else None


class FakeGenerator:
    def __init__(self):
        self.calls = 0

    async def stream(self, recipe, question=None):
        self.calls += 1
        yield "第一段"
        yield "第二段"


class FakeReadiness:
    def __init__(self, ready=True):
        self.ready = ready

    async def check(self):
        return ReadinessReport(
            ready=self.ready,
            components={"indexes": ComponentStatus(available=self.ready)},
        )


def client(ready=True):
    generator = FakeGenerator()
    app = create_app(FakeService(), FakeReadiness(ready), generator, mount_web=False)
    return TestClient(app), generator


def test_search_rejects_blank_query():
    test_client, _ = client()

    response = test_client.post("/api/v1/search", json={"query": "   "})

    assert response.status_code == 422


def test_recipe_detail_does_not_call_generator():
    test_client, generator = client()

    response = test_client.get("/api/v1/recipes/r1")

    assert response.status_code == 200
    assert generator.calls == 0


def test_missing_recipe_returns_404():
    test_client, _ = client()

    response = test_client.get("/api/v1/recipes/missing")

    assert response.status_code == 404


def test_ready_reports_manifest_mismatch():
    test_client, _ = client(ready=False)

    response = test_client.get("/ready")

    assert response.status_code == 503
    assert response.json()["ready"] is False


def test_stream_answer_is_separate_from_recipe_detail():
    test_client, generator = client()

    response = test_client.post("/api/v1/recipes/r1/answer/stream", json={"question": "怎么做"})

    assert response.status_code == 200
    assert response.text == "第一段第二段"
    assert generator.calls == 1


def test_health_only_checks_process_liveness():
    test_client, _ = client(ready=False)

    assert test_client.get("/health").json() == {
        "status": "ok",
        "service": "CookQA",
        "version": "0.1.0",
    }
