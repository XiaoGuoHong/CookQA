from __future__ import annotations

import asyncio
from typing import Any

from cookqa.models import Recipe


_UPSERT_CYPHER = """
UNWIND $recipes AS item
MERGE (recipe:Recipe {recipe_id: item.recipe_id})
SET recipe.name = item.name,
    recipe.aliases = item.aliases,
    recipe.summary = item.summary,
    recipe.difficulty = item.difficulty,
    recipe.calories = item.calories,
    recipe.duration_minutes = item.duration_minutes,
    recipe.steps = item.steps,
    recipe.source_path = item.source_path,
    recipe.source_version = item.source_version,
    recipe.data_version = $data_version
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


class Neo4jGraphWriter:
    def __init__(self, driver: Any, database: str | None = None):
        self.driver = driver
        self.database = database

    def _replace_sync(self, recipes: list[Recipe], data_version: str) -> set[str]:
        payload = [recipe.model_dump() for recipe in recipes]
        self.driver.execute_query(
            "MATCH (recipe:Recipe) DETACH DELETE recipe",
            database_=self.database,
        )
        self.driver.execute_query(
            _UPSERT_CYPHER,
            recipes=payload,
            data_version=data_version,
            database_=self.database,
        )
        records, _, _ = self.driver.execute_query(
            "MATCH (recipe:Recipe {data_version: $data_version}) RETURN recipe.recipe_id AS recipe_id",
            data_version=data_version,
            database_=self.database,
        )
        return {record["recipe_id"] for record in records}

    async def replace_recipes(self, recipes: list[Recipe], data_version: str) -> set[str]:
        return await asyncio.to_thread(self._replace_sync, recipes, data_version)
