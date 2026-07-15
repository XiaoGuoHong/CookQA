from __future__ import annotations

import asyncio
from typing import Any

from cookqa.models import Recipe

_SCHEMA_STATEMENTS = (
    (
        "CREATE CONSTRAINT cookqa_recipe_version_unique IF NOT EXISTS "
        "FOR (recipe:Recipe) "
        "REQUIRE (recipe.recipe_id, recipe.data_version) IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT cookqa_ingredient_name_unique IF NOT EXISTS "
        "FOR (node:Ingredient) REQUIRE node.name IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT cookqa_category_name_unique IF NOT EXISTS "
        "FOR (node:Category) REQUIRE node.name IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT cookqa_method_name_unique IF NOT EXISTS "
        "FOR (node:Method) REQUIRE node.name IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT cookqa_tool_name_unique IF NOT EXISTS "
        "FOR (node:Tool) REQUIRE node.name IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT cookqa_tag_name_unique IF NOT EXISTS "
        "FOR (node:Tag) REQUIRE node.name IS UNIQUE"
    ),
    (
        "CREATE INDEX cookqa_recipe_data_version IF NOT EXISTS "
        "FOR (recipe:Recipe) ON (recipe.data_version)"
    ),
)
_EXPECTED_CONSTRAINT_NAMES = {
    "cookqa_recipe_version_unique",
    "cookqa_ingredient_name_unique",
    "cookqa_category_name_unique",
    "cookqa_method_name_unique",
    "cookqa_tool_name_unique",
    "cookqa_tag_name_unique",
}
_EXPECTED_INDEX_NAMES = {"cookqa_recipe_data_version"}

_UPSERT_CYPHER = """
UNWIND $recipes AS item
MERGE (recipe:Recipe {recipe_id: item.recipe_id, data_version: $data_version})
SET recipe.name = item.name,
    recipe.aliases = item.aliases,
    recipe.summary = item.summary,
    recipe.difficulty = item.difficulty,
    recipe.calories = item.calories,
    recipe.duration_minutes = item.duration_minutes,
    recipe.steps = item.steps,
    recipe.source_path = item.source_path,
    recipe.source_version = item.source_version
WITH recipe, item
FOREACH (ingredient IN item.ingredients |
  MERGE (node:Ingredient {name: ingredient.name})
  MERGE (recipe)-[relation:REQUIRES]->(node)
  SET relation = ingredient.relationship_properties)
FOREACH (name IN item.categories |
  MERGE (node:Category {name: name})
  MERGE (recipe)-[:BELONGS_TO]->(node))
FOREACH (name IN item.methods |
  MERGE (node:Method {name: name})
  MERGE (recipe)-[:USES_METHOD]->(node))
FOREACH (name IN item.tools |
  MERGE (node:Tool {name: name})
  MERGE (recipe)-[:USES_TOOL]->(node))
FOREACH (name IN item.tags |
  MERGE (node:Tag {name: name})
  MERGE (recipe)-[:HAS_TAG]->(node))
"""

_VERSION_IDS_CYPHER = """
MATCH (recipe:Recipe {data_version: $data_version})
RETURN recipe.recipe_id AS recipe_id
"""

_DELETE_VERSION_CYPHER = """
MATCH (recipe:Recipe {data_version: $data_version})
DETACH DELETE recipe
"""

_CLEANUP_VERSIONS_CYPHER = """
MATCH (recipe:Recipe)
WHERE NOT recipe.data_version IN $keep_versions
DETACH DELETE recipe
"""


def _recipe_payload(recipe: Recipe) -> dict[str, Any]:
    item = recipe.model_dump()
    for ingredient in item["ingredients"]:
        ingredient["relationship_properties"] = {
            key: ingredient[key]
            for key in ("amount", "unit", "optional", "raw")
            if ingredient[key] is not None
        }
    return item


class Neo4jGraphWriter:
    def __init__(self, driver: Any, database: str | None = None):
        self.driver = driver
        self.database = database

    def _ensure_schema_sync(self) -> None:
        for statement in _SCHEMA_STATEMENTS:
            self.driver.execute_query(statement, database_=self.database)

        records, _, _ = self.driver.execute_query(
            "SHOW CONSTRAINTS YIELD name WHERE name IN $names RETURN name",
            names=sorted(_EXPECTED_CONSTRAINT_NAMES),
            database_=self.database,
        )
        actual_constraints = {record["name"] for record in records}
        missing_constraints = _EXPECTED_CONSTRAINT_NAMES - actual_constraints
        if missing_constraints:
            raise RuntimeError(
                f"Neo4j 约束校验失败: {sorted(missing_constraints)}"
            )

        records, _, _ = self.driver.execute_query(
            "SHOW INDEXES YIELD name WHERE name IN $names RETURN name",
            names=sorted(_EXPECTED_INDEX_NAMES),
            database_=self.database,
        )
        actual_indexes = {record["name"] for record in records}
        missing_indexes = _EXPECTED_INDEX_NAMES - actual_indexes
        if missing_indexes:
            raise RuntimeError(f"Neo4j 索引校验失败: {sorted(missing_indexes)}")

    def _write_sync(self, recipes: list[Recipe], data_version: str) -> None:
        payload = [_recipe_payload(recipe) for recipe in recipes]
        self.driver.execute_query(
            _UPSERT_CYPHER,
            recipes=payload,
            data_version=data_version,
            database_=self.database,
        )

    def _validate_sync(
        self,
        recipes: list[Recipe],
        data_version: str,
    ) -> set[str]:
        records, _, _ = self.driver.execute_query(
            _VERSION_IDS_CYPHER,
            data_version=data_version,
            database_=self.database,
        )
        actual = {record["recipe_id"] for record in records}
        expected = {recipe.recipe_id for recipe in recipes}
        if actual != expected:
            raise ValueError("Neo4j recipe_id 集合与候选版本不一致")
        return actual

    def _delete_sync(self, data_version: str) -> None:
        self.driver.execute_query(
            _DELETE_VERSION_CYPHER,
            data_version=data_version,
            database_=self.database,
        )

    def _cleanup_sync(self, keep_versions: set[str]) -> None:
        if not keep_versions:
            raise ValueError("Neo4j 清理时必须至少保留一个版本")
        self.driver.execute_query(
            _CLEANUP_VERSIONS_CYPHER,
            keep_versions=sorted(keep_versions),
            database_=self.database,
        )

    async def ensure_schema(self) -> None:
        await asyncio.to_thread(self._ensure_schema_sync)

    async def write_version(self, recipes: list[Recipe], data_version: str) -> None:
        await asyncio.to_thread(self._write_sync, recipes, data_version)

    async def validate_version(
        self,
        recipes: list[Recipe],
        data_version: str,
    ) -> set[str]:
        return await asyncio.to_thread(self._validate_sync, recipes, data_version)

    async def delete_version(self, data_version: str) -> None:
        await asyncio.to_thread(self._delete_sync, data_version)

    async def cleanup_versions(self, keep_versions: set[str]) -> None:
        await asyncio.to_thread(self._cleanup_sync, keep_versions)
