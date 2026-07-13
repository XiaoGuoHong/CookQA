from pathlib import Path

import pytest

from cookqa.ingest.normalize import stable_recipe_id
from cookqa.ingest.parser import RecipeParseError, parse_recipe
from cookqa.ingest.selection import load_selection

SAMPLE = Path(__file__).parent / "fixtures" / "howtocook" / "sample.md"


def test_recipe_id_is_stable_for_normalized_relative_path():
    assert stable_recipe_id("dishes/meat/宫保鸡丁.md") == stable_recipe_id(
        "dishes\\meat\\宫保鸡丁.md"
    )


def test_parser_preserves_raw_ingredient_and_normalizes_alias():
    recipe = parse_recipe(
        SAMPLE,
        source_root=SAMPLE.parent,
        source_version="abc123",
        aliases={"西红柿": "番茄"},
    )

    assert recipe.name == "番茄炒蛋"
    assert recipe.ingredients[0].name == "番茄"
    assert "西红柿" in recipe.ingredients[0].raw
    assert recipe.duration_minutes == 15
    assert recipe.source_version == "abc123"
    assert len(recipe.steps) == 3


def test_parser_fails_instead_of_silently_skipping_invalid_recipe(tmp_path):
    invalid = tmp_path / "invalid.md"
    invalid.write_text("# 只有标题", encoding="utf-8")

    with pytest.raises(RecipeParseError, match="invalid.md"):
        parse_recipe(invalid, tmp_path, "abc123", {})


def test_selection_rejects_duplicates_and_comments_are_ignored(tmp_path):
    selection = tmp_path / "selection.txt"
    selection.write_text("# comment\ndishes/a.md\ndishes/a.md\n", encoding="utf-8")

    with pytest.raises(ValueError, match="重复"):
        load_selection(selection)
