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
from tests.http_client import asgi_client


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


def app(ready=True):
    generator = FakeGenerator()
    application = create_app(FakeService(), FakeReadiness(ready), generator, mount_web=False)
    return application, generator


async def test_search_rejects_blank_query():
    application, _ = app()

    async with asgi_client(application) as client:
        response = await client.post("/api/v1/search", json={"query": "   "})

    assert response.status_code == 422


async def test_recipe_detail_does_not_call_generator():
    application, generator = app()

    async with asgi_client(application) as client:
        response = await client.get("/api/v1/recipes/r1")

    assert response.status_code == 200
    assert generator.calls == 0


async def test_missing_recipe_returns_404():
    application, _ = app()

    async with asgi_client(application) as client:
        response = await client.get("/api/v1/recipes/missing")

    assert response.status_code == 404


async def test_ready_reports_manifest_mismatch():
    application, _ = app(ready=False)

    async with asgi_client(application) as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["ready"] is False


async def test_stream_answer_is_separate_from_recipe_detail():
    application, generator = app()

    async with asgi_client(application) as client:
        response = await client.post(
            "/api/v1/recipes/r1/answer/stream",
            json={"question": "怎么做"},
        )

    assert response.status_code == 200
    assert response.text == "第一段第二段"
    assert generator.calls == 1


async def test_health_only_checks_process_liveness():
    application, _ = app(ready=False)

    async with asgi_client(application) as client:
        response = await client.get("/health")

    assert response.json() == {
        "status": "ok",
        "service": "CookQA",
        "version": "0.1.0",
    }


class FakePantryMatcher:
    def __init__(self):
        self.calls = []
        self.aliases = {"西红柿": "番茄"}

    def match(self, existing, excluded, **kwargs):
        from cookqa.models import PantrySearchResponse

        self.calls.append((existing, excluded, kwargs))
        return PantrySearchResponse(normalized_existing=["番茄"], ready=[])


def pantry_app():
    matcher = FakePantryMatcher()
    application = create_app(
        FakeService(), FakeReadiness(), FakeGenerator(), mount_web=False, pantry_matcher=matcher
    )
    return application, matcher


async def test_pantry_search_validates_and_maps_structured_request():
    application, matcher = pantry_app()

    async with asgi_client(application) as client:
        response = await client.post(
            "/api/v1/pantry/search",
            json={
                "existing_ingredients": [" 西红柿 "],
                "excluded_ingredients": ["葱"],
                "max_minutes": 30,
                "no_spicy": True,
                "use_pantry_staples": False,
            },
        )

    assert response.status_code == 200
    assert matcher.calls == [
        (["西红柿"], ["葱"], {"max_minutes": 30, "no_spicy": True, "use_staples": False})
    ]


async def test_pantry_search_rejects_missing_or_conflicting_ingredients():
    application, _ = pantry_app()

    async with asgi_client(application) as client:
        missing = await client.post("/api/v1/pantry/search", json={"existing_ingredients": []})
        conflict = await client.post(
            "/api/v1/pantry/search",
            json={"existing_ingredients": ["番茄"], "excluded_ingredients": ["西红柿"]},
        )

    assert missing.status_code == 422
    assert conflict.status_code == 422
