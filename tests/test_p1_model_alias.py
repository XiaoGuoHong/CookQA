import asyncio

from cookqa.config import Settings
from cookqa.runtime import RuntimeReadiness


class TaggedOllama:
    settings = Settings(embedding_model="bge-m3", chat_model="qwen3.5:4b")

    async def available_models(self):
        return {"bge-m3:latest", "qwen3.5:4b"}


def test_readiness_accepts_ollama_latest_tag_for_untagged_model_name():
    readiness = RuntimeReadiness(
        manifest=None,
        bm25=None,
        vector_index=None,
        neo4j_driver=None,
        ollama=TaggedOllama(),
    )

    report = asyncio.run(readiness.check())

    assert report.components["ollama"].available is True
