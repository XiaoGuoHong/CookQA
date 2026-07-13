import asyncio
import json

import httpx

from cookqa.config import Settings
from cookqa.generation.ollama import OllamaClient
from cookqa.models import Ingredient, Recipe


def recipe():
    return Recipe(
        recipe_id="r1",
        name="番茄炒蛋",
        ingredients=[Ingredient(name="番茄", raw="番茄 2 个")],
        steps=["炒熟"],
        source_path="dishes/tomato.md",
        source_version="abc",
    )


def test_embedding_uses_configured_local_model():
    async def handler(request):
        payload = json.loads(request.content)
        assert payload["model"] == "bge-m3"
        return httpx.Response(200, json={"embeddings": [[1.0, 2.0]]})

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="http://ollama") as http:
            client = OllamaClient(Settings(), http=http)
            return await client.embed("番茄炒蛋")

    assert asyncio.run(run()) == [1.0, 2.0]


def test_generation_prompt_contains_only_structured_recipe_context():
    captured = {}

    async def handler(request):
        captured.update(json.loads(request.content))
        body = '{"response":"第一段","done":false}\n{"response":"第二段","done":true}\n'
        return httpx.Response(200, content=body.encode("utf-8"))

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="http://ollama") as http:
            client = OllamaClient(Settings(), http=http)
            return [chunk async for chunk in client.stream(recipe(), "怎么做")]

    assert asyncio.run(run()) == ["第一段", "第二段"]
    assert captured["model"] == "qwen3.5:4b"
    assert "番茄炒蛋" in captured["prompt"]
    assert "炒熟" in captured["prompt"]
