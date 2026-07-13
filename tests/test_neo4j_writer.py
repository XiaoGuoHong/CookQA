import asyncio

import pytest

from cookqa.indexing.neo4j_writer import Neo4jGraphWriter
from cookqa.models import Ingredient, Recipe


class RecordingDriver:
    def __init__(self, ids=None):
        self.ids = list(ids or [])
        self.calls = []

    def execute_query(self, cypher, **parameters):
        self.calls.append((cypher, parameters))
        if "RETURN recipe.recipe_id AS recipe_id" in cypher:
            return ([{"recipe_id": item} for item in self.ids], None, None)
        return ([], None, None)


def recipe(recipe_id="r1"):
    return Recipe(
        recipe_id=recipe_id,
        name="番茄炒蛋",
        ingredients=[Ingredient(name="番茄", raw="番茄")],
        source_path="dishes/tomato.md",
        source_version="abc",
    )


def test_writer_keeps_recipe_versions_isolated():
    item = recipe()
    driver = RecordingDriver([item.recipe_id])
    writer = Neo4jGraphWriter(driver)

    asyncio.run(writer.write_version([item], "v2"))
    ids = asyncio.run(writer.validate_version([item], "v2"))

    all_cypher = "\n".join(call[0] for call in driver.calls)
    assert "recipe_id: item.recipe_id, data_version: $data_version" in all_cypher
    assert "MATCH (recipe:Recipe) DETACH DELETE recipe" not in all_cypher
    assert ids == {item.recipe_id}


def test_validation_rejects_different_recipe_ids():
    item = recipe()
    writer = Neo4jGraphWriter(RecordingDriver(["unexpected"]))

    with pytest.raises(ValueError, match="候选版本不一致"):
        asyncio.run(writer.validate_version([item], "v2"))


def test_delete_version_is_scoped():
    driver = RecordingDriver()
    writer = Neo4jGraphWriter(driver)

    asyncio.run(writer.delete_version("candidate"))

    cypher, parameters = driver.calls[-1]
    assert "data_version: $data_version" in cypher
    assert parameters["data_version"] == "candidate"


def test_cleanup_versions_is_parameterized():
    driver = RecordingDriver()
    writer = Neo4jGraphWriter(driver)

    asyncio.run(writer.cleanup_versions({"v2", "v1"}))

    cypher, parameters = driver.calls[-1]
    assert "NOT recipe.data_version IN $keep_versions" in cypher
    assert parameters["keep_versions"] == ["v1", "v2"]


def test_cleanup_rejects_empty_keep_set():
    writer = Neo4jGraphWriter(RecordingDriver())

    with pytest.raises(ValueError, match="至少保留一个版本"):
        asyncio.run(writer.cleanup_versions(set()))
