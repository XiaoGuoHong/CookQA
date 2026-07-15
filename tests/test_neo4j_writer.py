import asyncio

import pytest

from cookqa.indexing.neo4j_writer import Neo4jGraphWriter
from cookqa.models import Ingredient, Recipe

EXPECTED_CONSTRAINTS = {
    "cookqa_recipe_version_unique",
    "cookqa_ingredient_name_unique",
    "cookqa_category_name_unique",
    "cookqa_method_name_unique",
    "cookqa_tool_name_unique",
    "cookqa_tag_name_unique",
}
EXPECTED_INDEXES = {"cookqa_recipe_data_version"}


class RecordingDriver:
    def __init__(self, ids=None):
        self.ids = list(ids or [])
        self.calls = []

    def execute_query(self, cypher, **parameters):
        self.calls.append((cypher, parameters))
        if "SHOW CONSTRAINTS" in cypher:
            return ([{"name": name} for name in EXPECTED_CONSTRAINTS], None, None)
        if "SHOW INDEXES" in cypher:
            return ([{"name": name} for name in EXPECTED_INDEXES], None, None)
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


def test_schema_setup_is_idempotent_and_validated():
    driver = RecordingDriver()
    writer = Neo4jGraphWriter(driver)

    asyncio.run(writer.ensure_schema())
    asyncio.run(writer.ensure_schema())

    cypher_calls = [call[0].strip() for call in driver.calls]
    create_calls = [cypher for cypher in cypher_calls if cypher.startswith("CREATE")]
    assert len(create_calls) == 14
    assert all("IF NOT EXISTS" in cypher for cypher in create_calls)
    assert sum("SHOW CONSTRAINTS" in cypher for cypher in cypher_calls) == 2
    assert sum("SHOW INDEXES" in cypher for cypher in cypher_calls) == 2


def test_writer_omits_nullable_relationship_properties():
    item = recipe()
    driver = RecordingDriver()
    writer = Neo4jGraphWriter(driver)

    asyncio.run(writer.write_version([item], "v2"))

    cypher, parameters = driver.calls[-1]
    ingredient = parameters["recipes"][0]["ingredients"][0]
    assert ingredient["relationship_properties"] == {
        "optional": False,
        "raw": "番茄",
    }
    assert "SET relation = ingredient.relationship_properties" in cypher


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
