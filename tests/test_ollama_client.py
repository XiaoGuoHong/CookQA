import httpx

from cookqa.ollama_client import OllamaClient


class FakeClient:
    requests = []

    def __init__(self, timeout):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json):
        self.requests.append((url, json, self.timeout))
        return httpx.Response(
            200,
            json={"embeddings": [[1.0, 0.0], [0.0, 1.0]]},
            request=httpx.Request("POST", url),
        )


def test_embed_texts_uses_modern_embed_endpoint(monkeypatch):
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)
    client = OllamaClient(
        base_url="http://ollama.local",
        embedding_model="bge-m3",
        chat_model="gpt-oss:120b-cloud",
        timeout=600,
        embed_batch_size=8,
    )

    vectors = client.embed_texts(["番茄炒蛋", "水煮牛肉"])

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert FakeClient.requests == [
        (
            "http://ollama.local/api/embed",
            {"model": "bge-m3", "input": ["番茄炒蛋", "水煮牛肉"]},
            600,
        )
    ]
