from cookqa.config import CookQASettings
from cookqa.models import RecipeDocument


def test_settings_from_env_uses_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setenv("COOKQA_DATA_DIR", str(tmp_path / "data"))

    settings = CookQASettings.from_env()

    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.embedding_model == "bge-m3"
    assert settings.chat_model == "gpt-oss:120b-cloud"
    assert settings.ollama_timeout == 600.0
    assert settings.data_dir == tmp_path / "data"
    assert settings.parsed_recipes_path == tmp_path / "data" / "parsed" / "recipes.json"
    assert settings.recipe_index_path == tmp_path / "data" / "indexes" / "recipes.faiss"
    assert settings.step_index_path == tmp_path / "data" / "indexes" / "steps.faiss"


def test_settings_from_env_allows_ollama_timeout_override(monkeypatch):
    monkeypatch.setenv("OLLAMA_TIMEOUT", "900")

    settings = CookQASettings.from_env()

    assert settings.ollama_timeout == 900.0


def test_recipe_document_builds_search_text():
    recipe = RecipeDocument(
        recipe_id="dishes/vegetable_dish/西红柿炒鸡蛋.md",
        name="西红柿炒鸡蛋",
        category="素菜",
        source_path="dishes/vegetable_dish/西红柿炒鸡蛋.md",
        source_url=None,
        description="酸甜开胃的家常菜",
        difficulty="★★",
        calories="252 大卡",
        ingredients=["西红柿", "鸡蛋", "盐"],
        tools=[],
        steps=["炒鸡蛋", "炒西红柿", "合炒"],
        notes=["可以加葱花"],
        raw_text="# 西红柿炒鸡蛋的做法",
    )

    assert "西红柿炒鸡蛋" in recipe.search_text()
    assert "西红柿 鸡蛋 盐" in recipe.search_text()
    assert recipe.summary_steps() == ["炒鸡蛋", "炒西红柿", "合炒"]
