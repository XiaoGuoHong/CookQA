from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from cookqa.config import CookQASettings
from cookqa.ollama_client import OllamaClient


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "howtocook"


def test_health_endpoint(tmp_path):
    client = TestClient(create_app(settings_for(tmp_path), ollama_client=None))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["service"] == "CookQA"


def test_default_app_factory_creates_ollama_client(tmp_path):
    app = create_app(settings_for(tmp_path))

    assert isinstance(app.state.cookqa_service.ollama_client, OllamaClient)


def test_chat_endpoint_returns_recommendations(tmp_path):
    settings = settings_for(tmp_path)
    app = create_app(settings, ollama_client=None)
    client = TestClient(app)
    client.post("/api/v1/index/rebuild", params={"vectors": "false"})

    response = client.post(
        "/api/v1/chat",
        json={"question": "番茄炒蛋怎么做", "top_k": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "dish_lookup"
    assert body["recommendations"][0]["name"] == "西红柿炒鸡蛋"


def test_search_endpoint_returns_ranked_items(tmp_path):
    settings = settings_for(tmp_path)
    app = create_app(settings, ollama_client=None)
    client = TestClient(app)
    client.post("/api/v1/index/rebuild", params={"vectors": "false"})

    response = client.get(
        "/api/v1/recipes/search",
        params={"q": "牛肉可以怎么做", "top_k": 5},
    )

    assert response.status_code == 200
    assert response.json()["recommendations"][0]["name"] == "水煮牛肉"


def settings_for(tmp_path):
    return CookQASettings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        howtocook_path=FIXTURE_ROOT,
        ollama_base_url="http://127.0.0.1:11434",
        embedding_model="bge-m3",
        chat_model="gpt-oss:120b-cloud",
        ollama_timeout=600.0,
        ollama_embed_batch_size=1,
        top_k=5,
        min_score=0.15,
        enable_rebuild_api=True,
    )
