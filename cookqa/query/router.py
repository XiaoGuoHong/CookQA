from __future__ import annotations

import re
from collections.abc import Mapping, Set

from cookqa.ingest.normalize import normalize_query_text
from cookqa.models import QueryConstraints, QueryPlan

_DURATION_RE = re.compile(r"(\d+)\s*分钟(?:内|以内|以下)?")
_STEP_TERMS = ("什么时候", "先放", "后放", "下锅", "火候", "几分钟", "怎么切")
_COMPARISON_TERMS = ("区别", "比较", "不同", "哪个好")
_SIMILAR_TERMS = ("相似", "类似", "像")
_RECOMMENDATION_TERMS = ("推荐", "想吃", "来点", "找")
_SUBJECTIVE_TAGS = ("清淡", "下饭", "适合夏天", "快手", "家常")


class QueryRouter:
    def __init__(
        self,
        recipe_names: Mapping[str, str],
        ingredient_names: Set[str],
        ingredient_aliases: Mapping[str, str] | None = None,
    ) -> None:
        self._recipe_names = {
            normalize_query_text(name): canonical for name, canonical in recipe_names.items()
        }
        self._ingredient_names = {normalize_query_text(name): name for name in ingredient_names}
        self._ingredient_aliases = {
            normalize_query_text(alias): canonical
            for alias, canonical in (ingredient_aliases or {}).items()
        }

    def _recognized_recipes(self, query: str) -> list[str]:
        found = [
            (query.index(name), canonical)
            for name, canonical in self._recipe_names.items()
            if name and name in query
        ]
        return list(dict.fromkeys(canonical for _, canonical in sorted(found)))

    def _recognized_ingredients(self, query: str) -> list[str]:
        found: list[tuple[int, str]] = []
        for name, canonical in self._ingredient_names.items():
            if name and name in query:
                found.append((query.index(name), canonical))
        for alias, canonical in self._ingredient_aliases.items():
            if alias and alias in query:
                found.append((query.index(alias), canonical))
        return list(dict.fromkeys(canonical for _, canonical in sorted(found)))

    @staticmethod
    def _excluded_ingredients(query: str, ingredients: list[str]) -> list[str]:
        excluded: list[str] = []
        for ingredient in ingredients:
            if any(
                token in query
                for token in (f"不含{ingredient}", f"不要{ingredient}", f"去掉{ingredient}")
            ):
                excluded.append(ingredient)
        if any(token in query for token in ("不辣", "不要辣", "免辣")):
            excluded.append("辣")
        return list(dict.fromkeys(excluded))

    @staticmethod
    def _constraints(query: str) -> QueryConstraints:
        duration = _DURATION_RE.search(query)
        subjective = [tag for tag in _SUBJECTIVE_TAGS if tag in query]
        tools = [tool for tool in ("烤箱", "空气炸锅", "微波炉", "高压锅") if tool in query]
        difficulties = [level for level in ("简单", "容易", "困难") if level in query]
        return QueryConstraints(
            max_minutes=int(duration.group(1)) if duration else None,
            tools=tools,
            difficulties=difficulties,
            subjective_tags=subjective,
        )

    def route(self, query: str) -> QueryPlan:
        original = query
        normalized = normalize_query_text(query)
        if not normalized:
            raise ValueError("查询不能为空")

        recipes = self._recognized_recipes(normalized)
        all_ingredients = self._recognized_ingredients(normalized)
        excluded = self._excluded_ingredients(normalized, all_ingredients)
        required = [item for item in all_ingredients if item not in excluded]
        constraints = self._constraints(normalized)

        common = {
            "original_query": original,
            "normalized_query": normalized,
            "recognized_recipes": recipes,
            "required_ingredients": required,
            "excluded_ingredients": excluded,
            "constraints": constraints,
        }

        if len(recipes) >= 2 and any(term in normalized for term in _COMPARISON_TERMS):
            return QueryPlan(
                **common,
                intent="recipe_comparison",
                retrieval_strategy=["neo4j"],
                confidence=0.98,
            )

        if recipes and any(term in normalized for term in _SIMILAR_TERMS):
            return QueryPlan(
                **common,
                intent="similar_recipe",
                retrieval_strategy=["faiss", "neo4j"],
                confidence=0.95,
            )

        if any(term in normalized for term in _STEP_TERMS) and not recipes:
            return QueryPlan(
                **common,
                intent="clarification_required",
                retrieval_strategy=[],
                confidence=1.0,
                clarification="请补充具体菜名，以免混合不同菜谱的操作步骤。",
            )

        if recipes:
            return QueryPlan(
                **common,
                intent="exact_recipe",
                retrieval_strategy=["exact"],
                confidence=1.0,
            )

        has_conditional_cue = constraints.has_hard_filters() or bool(excluded)
        if has_conditional_cue or "推荐" in normalized:
            return QueryPlan(
                **common,
                intent="conditional_recommendation",
                retrieval_strategy=["neo4j", "bm25", "faiss"],
                confidence=0.9 if has_conditional_cue else 0.7,
            )

        if required and (len(required) >= 2 or "能做什么" in normalized or "做什么" in normalized):
            return QueryPlan(
                **common,
                intent="ingredient_lookup",
                retrieval_strategy=["neo4j", "bm25", "faiss"],
                confidence=0.9,
            )

        return QueryPlan(
            **common,
            intent="semantic_recommendation",
            retrieval_strategy=["faiss", "bm25"],
            confidence=0.65 if any(term in normalized for term in _RECOMMENDATION_TERMS) else 0.5,
        )
