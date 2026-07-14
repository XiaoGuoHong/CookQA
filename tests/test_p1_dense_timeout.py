from cookqa.config import Settings


def test_default_dense_timeout_allows_local_embedding_cold_start(monkeypatch):
    monkeypatch.delenv("COOKQA_DENSE_TIMEOUT", raising=False)

    settings = Settings.from_env()

    assert settings.dense_timeout_seconds == 6.0
