from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from cookqa.config import Settings
from cookqa.models import Recipe


class OllamaUnavailable(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None):
        self.settings = settings
        self._http = http

    def _client(self) -> tuple[httpx.AsyncClient, bool]:
        if self._http is not None:
            return self._http, False
        return (
            httpx.AsyncClient(
                base_url=self.settings.ollama_base_url,
                timeout=self.settings.request_timeout_seconds,
            ),
            True,
        )

    async def embed(self, text: str) -> list[float]:
        client, owned = self._client()
        try:
            response = await client.post(
                "/api/embed",
                json={"model": self.settings.embedding_model, "input": text},
            )
            response.raise_for_status()
            embeddings = response.json().get("embeddings") or []
            if not embeddings or not embeddings[0]:
                raise OllamaUnavailable("Ollama 未返回向量")
            return [float(value) for value in embeddings[0]]
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise OllamaUnavailable("Ollama Embedding 不可用") from exc
        finally:
            if owned:
                await client.aclose()

    @staticmethod
    def _prompt(recipe: Recipe, question: str | None) -> str:
        context = {
            "菜名": recipe.name,
            "别名": recipe.aliases,
            "分类": recipe.categories,
            "简介": recipe.summary,
            "食材": [ingredient.model_dump() for ingredient in recipe.ingredients],
            "难度": recipe.difficulty,
            "耗时分钟": recipe.duration_minutes,
            "工具": recipe.tools,
            "步骤": recipe.steps,
            "来源": recipe.source_path,
        }
        return (
            "你是 CookQA。只能依据下面的结构化菜谱回答，不得补造缺失信息；"
            "如果信息不足，请明确说明。\n"
            f"菜谱：{json.dumps(context, ensure_ascii=False)}\n"
            f"用户问题：{question or '请简洁说明这道菜的做法。'}"
        )

    async def stream(self, recipe: Recipe, question: str | None = None) -> AsyncIterator[str]:
        client, owned = self._client()
        try:
            async with client.stream(
                "POST",
                "/api/generate",
                json={
                    "model": self.settings.chat_model,
                    "prompt": self._prompt(recipe, question),
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    payload = json.loads(line)
                    chunk = payload.get("response")
                    if chunk:
                        yield str(chunk)
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise OllamaUnavailable("Ollama 生成服务不可用") from exc
        finally:
            if owned:
                await client.aclose()

    async def available_models(self) -> set[str]:
        client, owned = self._client()
        try:
            response = await client.get("/api/tags")
            response.raise_for_status()
            return {str(item.get("name")) for item in response.json().get("models", [])}
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise OllamaUnavailable("Ollama 不可用") from exc
        finally:
            if owned:
                await client.aclose()
