import pytest
from pydantic import ValidationError

from cookqa.models import Ingredient, Recipe


def make_recipe(**overrides):
    values = {
        "recipe_id": "recipe-1",
        "name": "番茄炒蛋",
        "ingredients": [Ingredient(name="番茄", raw="西红柿 2 个")],
        "source_path": "dishes/vegetable/番茄炒蛋.md",
        "source_version": "abc123",
    }
    values.update(overrides)
    return Recipe(**values)


def test_recipe_rejects_duplicate_ingredient_names():
    with pytest.raises(ValidationError):
        make_recipe(
            ingredients=[
                Ingredient(name="鸡蛋", raw="鸡蛋 1 个"),
                Ingredient(name="鸡蛋", raw="鸡蛋 2 个"),
            ]
        )


def test_recipe_requires_a_source_path_and_version():
    with pytest.raises(ValidationError):
        make_recipe(source_path="")

    with pytest.raises(ValidationError):
        make_recipe(source_version="")
