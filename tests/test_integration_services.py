from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.integration


def base_url() -> str:
    return os.getenv(
        "COOKQA_INTEGRATION_BASE_URL",
        "http://127.0.0.1:8000",
    ).rstrip("/")


async def test_real_service_is_ready_with_200_recipe_manifest():
    async with httpx.AsyncClient(base_url=base_url(), timeout=30) as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["manifest"]["recipe_count"] == 200
    assert all(item["available"] for item in payload["components"].values())


async def test_real_search_uses_no_degraded_components():
    async with httpx.AsyncClient(base_url=base_url(), timeout=30) as client:
        response = await client.post(
            "/api/v1/search",
            json={"query": "可乐鸡翅怎么做"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    assert payload["degradation"]["degraded"] is False
    assert payload["degradation"]["unavailable_components"] == []
