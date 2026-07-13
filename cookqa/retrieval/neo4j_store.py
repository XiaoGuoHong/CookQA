from __future__ import annotations

import asyncio
from typing import Any

from cookqa.models import QueryPlan, RankedCandidate


def build_candidate_query(plan: QueryPlan, limit: int) -> tuple[str, dict[str, Any]]:
    cypher = """
    MATCH (recipe:Recipe)
    WHERE ($required_ingredients = [] OR ALL(name IN $required_ingredients WHERE
      EXISTS { MATCH (recipe)-[:REQUIRES]->(required:Ingredient) WHERE required.name = name }))
      AND ($excluded_ingredients = [] OR NONE(name IN $excluded_ingredients WHERE
      EXISTS { MATCH (recipe)-[:REQUIRES]->(excluded:Ingredient) WHERE excluded.name = name }))
      AND ($max_minutes IS NULL OR (recipe.duration_minutes IS NOT NULL
        AND recipe.duration_minutes <= $max_minutes))
      AND ($categories = [] OR EXISTS {
        MATCH (recipe)-[:BELONGS_TO]->(category:Category) WHERE category.name IN $categories
      })
      AND ($tools = [] OR ALL(name IN $tools WHERE
        EXISTS { MATCH (recipe)-[:USES_TOOL]->(tool:Tool) WHERE tool.name = name }))
    OPTIONAL MATCH (recipe)-[:REQUIRES]->(ingredient:Ingredient)
    WITH recipe, count(ingredient) AS relation_count
    RETURN recipe.recipe_id AS recipe_id, relation_count
    ORDER BY relation_count DESC, recipe.recipe_id
    LIMIT $limit
    """
    parameters = {
        "required_ingredients": plan.required_ingredients,
        "excluded_ingredients": plan.excluded_ingredients,
        "max_minutes": plan.constraints.max_minutes,
        "categories": plan.constraints.categories,
        "tools": plan.constraints.tools,
        "limit": limit,
    }
    return cypher, parameters


class Neo4jRetriever:
    name = "neo4j"

    def __init__(self, driver: Any, database: str | None = None):
        self.driver = driver
        self.database = database

    def _search_sync(self, plan: QueryPlan, limit: int) -> list[RankedCandidate]:
        cypher, parameters = build_candidate_query(plan, limit)
        records, _, _ = self.driver.execute_query(
            cypher,
            parameters_=parameters,
            database_=self.database,
        )
        return [
            RankedCandidate(
                recipe_id=record["recipe_id"],
                score=float(record.get("relation_count", 0)),
                source=self.name,
                reasons=["图关系与硬条件匹配"],
            )
            for record in records
        ]

    async def search(self, plan: QueryPlan, limit: int) -> list[RankedCandidate]:
        return await asyncio.to_thread(self._search_sync, plan, limit)
