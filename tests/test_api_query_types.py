import pytest

from api.app import create_app
from cookqa.models import (
    ComponentStatus,
    Ingredient,
    RankedCandidate,
    ReadinessReport,
    Recipe,
)
from cookqa.query.router import QueryRouter
from cookqa.retrieval.coordinator import RetrievalCoordinator
from cookqa.service import SearchService
from tests.http_client import asgi_client


class FakeRetriever:
    def __init__(self, name):
        self.name = name

    async def search(self, plan, limit):
        return [
            RankedCandidate(
                recipe_id="r1",
                score=1.0,
                source=self.name,
                reasons=[f"{self.name} 命中"],
            )
        ]


class FakeReadiness:
    async def check(self):
        return ReadinessReport(
            ready=True,
            components={"indexes": ComponentStatus(available=True)},
        )


class FakeGenerator:
    async def stream(self, recipe, question=None):
        yield "unused"


def recipe(recipe_id, name, ingredients, *, aliases=None, duration=15):
    return Recipe(
        recipe_id=recipe_id,
        name=name,
        aliases=aliases or [],
        ingredients=[Ingredient(name=item, raw=item) for item in ingredients],
        categories=["家常菜"],
        methods=["炒"],
        tools=["炒锅"],
        difficulty="简单",
        duration_minutes=duration,
        source_path=f"dishes/{recipe_id}.md",
        source_version="abc",
    )


def app():
    recipes = {
        "r1": recipe("r1", "番茄炒蛋", ["番茄", "鸡蛋"], aliases=["西红柿炒鸡蛋"]),
        "r2": recipe("r2", "宫保鸡丁", ["鸡肉", "花生"]),
        "r3": recipe("r3", "辣子鸡", ["鸡肉", "干辣椒"], duration=35),
    }
    names = {
        name: recipe_item.name
        for recipe_item in recipes.values()
        for name in [recipe_item.name, *recipe_item.aliases]
    }
    ingredients = {
        ingredient.name
        for recipe_item in recipes.values()
        for ingredient in recipe_item.ingredients
    }
    router = QueryRouter(names, ingredients)
    coordinator = RetrievalCoordinator(
        recipes,
        [FakeRetriever("bm25"), FakeRetriever("faiss"), FakeRetriever("neo4j")],
    )
    service = SearchService(router, coordinator, recipes)
    return create_app(service, FakeReadiness(), FakeGenerator(), mount_web=False)


@pytest.mark.parametrize(
    ("query", "intent"),
    [
        ("番茄炒蛋怎么做", "exact_recipe"),
        ("鸡蛋和番茄能做什么", "ingredient_lookup"),
        ("推荐20分钟内的菜", "conditional_recommendation"),
        ("想吃温暖的菜", "semantic_recommendation"),
        ("找和番茄炒蛋相似的菜", "similar_recipe"),
        ("宫保鸡丁和辣子鸡有什么区别", "recipe_comparison"),
    ],
)
async def test_six_query_types_have_service_and_api_behavior(query, intent):
    async with asgi_client(app()) as client:
        response = await client.post("/api/v1/search", json={"query": query})

    assert response.status_code == 200
    assert response.json()["query_plan"]["intent"] == intent


async def test_comparison_api_returns_two_targets_and_structured_differences():
    async with asgi_client(app()) as client:
        response = await client.post(
            "/api/v1/search",
            json={"query": "宫保鸡丁和辣子鸡有什么区别"},
        )
    payload = response.json()

    assert response.status_code == 200
    assert [item["recipe"]["name"] for item in payload["results"]] == [
        "宫保鸡丁",
        "辣子鸡",
    ]
    assert payload["comparison"]["ingredients"]["common"] == ["鸡肉"]
    assert payload["comparison"]["duration_minutes"]["left"] == 15
    assert payload["comparison"]["duration_minutes"]["right"] == 35
