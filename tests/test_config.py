from cookqa.config import Settings


def test_settings_use_local_safe_defaults(monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    settings = Settings.from_env()

    assert settings.host == "127.0.0.1"
    assert settings.chat_model == "qwen3.5:4b"
    assert settings.embedding_model == "bge-m3"
    assert settings.neo4j_password is None


def test_settings_read_sensitive_values_without_exposing_them(monkeypatch):
    monkeypatch.setenv("NEO4J_PASSWORD", "test-only-secret")

    settings = Settings.from_env()

    assert settings.neo4j_password == "test-only-secret"
    assert "test-only-secret" not in repr(settings)
