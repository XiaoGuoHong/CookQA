from pathlib import Path

import pytest

from cookqa.config import CookQASettings
from cookqa.service import CookQAService


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "howtocook"


def settings_for(tmp_path):
    return CookQASettings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        howtocook_path=FIXTURE_ROOT,
        ollama_base_url="http://127.0.0.1:11434",
        embedding_model="bge-m3",
        chat_model="gpt-oss:120b-cloud",
        top_k=5,
        min_score=0.15,
        enable_rebuild_api=True,
    )


def test_service_rebuild_writes_metadata_without_live_ollama(tmp_path):
    service = CookQAService.from_settings(settings_for(tmp_path), ollama_client=None)

    result = service.rebuild_metadata()

    assert result["recipes"] == 2
    assert (tmp_path / "data" / "parsed" / "recipes.json").exists()
    assert (tmp_path / "data" / "graph" / "relations.json").exists()


def test_service_chat_returns_answer_and_sources(tmp_path):
    service = CookQAService.from_settings(settings_for(tmp_path), ollama_client=None)
    service.rebuild_metadata()

    result = service.chat("番茄炒蛋怎么做", top_k=3, include_steps=True)

    assert result.mode == "dish_lookup"
    assert result.recommendations[0].name == "西红柿炒鸡蛋"
    assert result.sources[0].name == "西红柿炒鸡蛋"


def test_get_recipe_raises_key_error_for_unknown_recipe(tmp_path):
    service = CookQAService.from_settings(settings_for(tmp_path), ollama_client=None)
    service.rebuild_metadata()

    with pytest.raises(KeyError):
        service.get_recipe("missing.md")
