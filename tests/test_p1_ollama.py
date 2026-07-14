import asyncio
import json

import httpx

from cookqa.config import Settings
from cookqa.generation.ollama import OllamaClient
from cookqa.models import Ingredient, Recipe


def test_generation_disables_thinking_for_low_first_token_latency():
    captured = {}
    recipe = Recipe(
        recipe_id="r1",
        name="番茄炒蛋",
        ingredients=[Ingredient(name="番茄", raw="番茄 2 个")],
        steps=["炒熟"],
        source_path="dishes/tomato.md",
        source_version="abc",
    )

    async def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, content=b'{"response":"ok","done":true}\n')

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="http://ollama") as http:
            client = OllamaClient(Settings(), http=http)
            return [chunk async for chunk in client.stream(recipe, "怎么做")]

    assert asyncio.run(run()) == ["ok"]
    assert captured["think"] is False
