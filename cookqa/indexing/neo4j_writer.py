from __future__ import annotations

import asyncio
from typing import Any

from cookqa.models import Recipe

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
  SET relation.amount = ingredient.amount,
      relation.unit = ingredient.unit,
      relation.optional = ingredient.optional,
      relation.raw = ingredient.raw)
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


class Neo4jGraphWriter:
    def __init__(self, driver: Any, database: str | None = None):
        self.driver = driver
        self.database = database

    def _write_sync(self, recipes: list[Recipe], data_version: str) -> None:
        payload = [recipe.model_dump() for recipe in recipes]
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
