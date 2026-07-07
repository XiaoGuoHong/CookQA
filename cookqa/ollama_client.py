from typing import Sequence

import httpx


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        embedding_model: str,
        chat_model: str,
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.embedding_model = embedding_model
        self.chat_model = chat_model
        self.timeout = timeout

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        with httpx.Client(timeout=self.timeout) as client:
            for text in texts:
                response = client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.embedding_model, "prompt": text},
                )
                response.raise_for_status()
                vectors.append(response.json()["embedding"])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def chat(self, prompt: str) -> str:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/generate",
                json={"model": self.chat_model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
