from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是数字") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    chat_model: str = "qwen3.5:4b"
    embedding_model: str = "bge-m3"
    ollama_base_url: str = "http://127.0.0.1:11434"
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = field(default=None, repr=False)
    data_dir: Path = Path("Data")
    request_timeout_seconds: float = 3.0
    dense_timeout_seconds: float = 0.75
    cache_ttl_seconds: int = 30

    @classmethod
    def from_env(cls) -> Settings:
        password = os.getenv("NEO4J_PASSWORD") or None
        return cls(
            host=os.getenv("COOKQA_HOST", "127.0.0.1"),
            port=_env_int("COOKQA_PORT", 8000),
            chat_model=os.getenv("COOKQA_CHAT_MODEL", "qwen3.5:4b"),
            embedding_model=os.getenv("COOKQA_EMBEDDING_MODEL", "bge-m3"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=password,
            data_dir=Path(os.getenv("COOKQA_DATA_DIR", "Data")),
            request_timeout_seconds=_env_float("COOKQA_REQUEST_TIMEOUT", 3.0),
            dense_timeout_seconds=_env_float("COOKQA_DENSE_TIMEOUT", 0.75),
            cache_ttl_seconds=_env_int("COOKQA_CACHE_TTL", 30),
        )
