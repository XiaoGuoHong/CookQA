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
_SUBJECTIVE_TAGS = ("清淡", "下饭", "适合夏天", "快手", "家常", "简单", "容易", "困难")
_NON_INGREDIENT_TERMS = {
    "\u6c34",
    "\u83dc",
    "\u8089",
    "\u9c7c",
    "\u65e9\u9910",
    "\u4e3b\u98df",
    "\u9762\u98df",
    "\u70e4\u7bb1",
    "\u7a7a\u6c14\u70b8\u9505",
    "\u5fae\u6ce2\u7089",
    "\u9ad8\u538b\u9505",
}


class QueryRouter:
    def __init__(
        self,
        recipe_names: Mapping[str, str],
        ingredient_names: Set[str],
        ingredient_aliases: Mapping[str, str] | None = None,
    ) -> None:
        self._recipe_names = {}
        for name, canonical in recipe_names.items():
            normalized_name = normalize_query_text(name)
            if normalized_name:
                self._recipe_names[normalized_name] = canonical
                for suffix in ("\u7684\u505a\u6cd5", "\u505a\u6cd5"):
                    if normalized_name.endswith(suffix) and len(normalized_name) > len(suffix):
                        self._recipe_names[normalized_name[: -len(suffix)]] = canonical
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
        selected: list[str] = []
        for _, canonical in sorted(found, key=lambda item: (item[0], -len(item[1]))):
            if any(canonical != existing and canonical in existing for existing in selected):
                continue
            selected.append(canonical)
        return list(dict.fromkeys(selected))

    def _recognized_ingredients(self, query: str) -> list[str]:
        found: list[tuple[int, str]] = []
        for name, canonical in self._ingredient_names.items():
            if (
                name
                and name not in _NON_INGREDIENT_TERMS
                and canonical not in _NON_INGREDIENT_TERMS
                and name in query
            ):
                found.append((query.index(name), canonical))
        for alias, canonical in self._ingredient_aliases.items():
            if alias and alias in query:
                found.append((query.index(alias), canonical))
        selected: list[str] = []
        for _, canonical in sorted(found, key=lambda item: (item[0], -len(item[1]))):
            if any(canonical != existing and canonical in existing for existing in selected):
                continue
            selected.append(canonical)
        return list(dict.fromkeys(selected))

    @staticmethod
    def _excluded_ingredients(query: str, ingredients: list[str]) -> list[str]:
        excluded: list[str] = []
        for ingredient in ingredients:
            if any(
                token in query
                for token in (
                    f"\u4e0d\u542b{ingredient}",
                    f"\u4e0d\u8981{ingredient}",
                    f"\u4e0d\u7528{ingredient}",
                    f"\u53bb\u6389{ingredient}",
                )
            ):
                excluded.append(ingredient)
        return list(dict.fromkeys(excluded))

    @staticmethod
    def _subjective_labels(query: str) -> tuple[list[str], list[str]]:
        if any(token in query for token in ("\u4e0d\u8fa3", "\u65e0\u8fa3", "\u514d\u8fa3")):
            return [], ["spicy"]
        if any(
            token in query
            for token in ("\u8fa3\u5473", "\u9999\u8fa3", "\u8fa3\u7684", "\u8fa3\u83dc")
        ):
            return ["spicy"], []
        return [], []

    @staticmethod
    def _constraints(query: str) -> QueryConstraints:
        duration = _DURATION_RE.search(query)
        subjective = [tag for tag in _SUBJECTIVE_TAGS if tag in query]
        required_labels, excluded_labels = QueryRouter._subjective_labels(query)
        tool_names = (
            "\u70e4\u7bb1",
            "\u7a7a\u6c14\u70b8\u9505",
            "\u5fae\u6ce2\u7089",
            "\u9ad8\u538b\u9505",
        )
        tools = [
            tool
            for tool in tool_names
            if tool in query
            and not any(
                token + tool in query for token in ("\u4e0d\u7528", "\u4e0d\u542b", "\u4e0d\u8981")
            )
        ]
        excluded_tools = [
            tool
            for tool in tool_names
            if any(
                token + tool in query for token in ("\u4e0d\u7528", "\u4e0d\u542b", "\u4e0d\u8981")
            )
        ]
        category_terms = {
            "\u6e05\u84b8": "aquatic",
            "\u6c34\u4ea7": "aquatic",
            "\u9c7c\u83dc": "aquatic",
            "\u867e\u83dc": "aquatic",
            "\u65e9\u9910": "breakfast",
            "\u4e3b\u98df": "staple",
            "\u9762\u98df": "staple",
            "\u6c64": "soup",
            "\u51c9\u83dc": "vegetable_dish",
            "\u7d20\u83dc": "vegetable_dish",
            "\u8304\u5b50\u83dc": "vegetable_dish",
            "\u8089\u83dc": "meat_dish",
        }
        categories = list(
            dict.fromkeys(value for term, value in category_terms.items() if term in query)
        )
        return QueryConstraints(
            max_minutes=int(duration.group(1)) if duration else None,
            tools=tools,
            excluded_tools=excluded_tools,
            subjective_tags=subjective,
            categories=categories,
            required_labels=required_labels,
            excluded_labels=excluded_labels,
        )

    def route(self, query: str) -> QueryPlan:
        original = query
        normalized = normalize_query_text(query)
        if not normalized:
            raise ValueError("查询不能为空")

        recipes = self._recognized_recipes(normalized)
        all_ingredients = self._recognized_ingredients(normalized)
        excluded = self._excluded_ingredients(normalized, all_ingredients)
        reference_ingredients = {
            item
            for item in all_ingredients
            if any(
                normalize_query_text(item) in normalize_query_text(recipe_name)
                for recipe_name in recipes
            )
        }
        required = [
            item
            for item in all_ingredients
            if item not in excluded and item not in reference_ingredients
        ]
        constraints = self._constraints(normalized)
        retrieval_query = normalized
        if "凉菜" in normalized and "凉拌" not in normalized:
            retrieval_query += " 凉拌"

        common = {
            "original_query": original,
            "normalized_query": retrieval_query,
            "recognized_recipes": recipes,
            "required_ingredients": required,
            "excluded_ingredients": excluded,
            "constraints": constraints,
        }
        comparison_requested = any(term in normalized for term in _COMPARISON_TERMS)

        if len(recipes) > 2 and comparison_requested:
            return QueryPlan(
                **common,
                intent="clarification_required",
                retrieval_strategy=[],
                confidence=1.0,
                clarification="一次只能比较两道菜，请保留两个菜名。",
            )

        if len(recipes) == 2 and comparison_requested:
            return QueryPlan(
                **common,
                intent="recipe_comparison",
                retrieval_strategy=["neo4j"],
                confidence=0.98,
            )

        if recipes and any(term in normalized for term in _SIMILAR_TERMS):
            similar_common = {
                **common,
                "constraints": constraints.model_copy(update={"categories": []}),
            }
            return QueryPlan(
                **similar_common,
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
