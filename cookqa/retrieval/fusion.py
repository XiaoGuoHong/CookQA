from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from cookqa.models import QueryConstraints, Recipe

_SPICY_MARKERS = (
    "\u8fa3\u6912",
    "\u8fa3\u6912\u7c89",
    "\u8fa3\u9171",
    "\u8c46\u74e3\u9171",
    "\u706b\u9505\u5e95\u6599",
)
_INGREDIENT_EQUIVALENTS = {
    "\u732a\u8089": ("\u732a\u8089", "\u4e94\u82b1\u8089"),
    "\u867e": ("\u867e", "\u5927\u867e", "\u867e\u4ec1", "\u7f57\u6c0f\u867e"),
    "\u7c73\u996d": ("\u7c73\u996d", "\u996d"),
}


def recipe_has_label(recipe: Recipe | dict, label: str) -> bool:
    if label != "spicy":
        return False
    ingredients = (
        recipe.ingredients if isinstance(recipe, Recipe) else recipe.get("ingredients", [])
    )
    values = [
        ingredient.name if isinstance(ingredient, dict) is False else ingredient.get("name", "")
        for ingredient in ingredients
    ]
    values.extend(recipe.tags if isinstance(recipe, Recipe) else recipe.get("tags", []))
    return any(marker in value for value in values for marker in _SPICY_MARKERS)


@dataclass(slots=True)
class FusedCandidate:
    recipe_id: str
    score: float = 0.0
    sources: list[str] = field(default_factory=list)


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[str]],
    weights: Mapping[str, float] | None = None,
    k: int = 60,
) -> list[FusedCandidate]:
    if k <= 0:
        raise ValueError("RRF k 必须大于 0")
    weights = weights or {}
    fused: dict[str, FusedCandidate] = {}
    for source, recipe_ids in rankings.items():
        weight = weights.get(source, 1.0)
        for rank, recipe_id in enumerate(recipe_ids, 1):
            candidate = fused.setdefault(recipe_id, FusedCandidate(recipe_id=recipe_id))
            candidate.score += weight / (k + rank)
            if source not in candidate.sources:
                candidate.sources.append(source)
    return sorted(fused.values(), key=lambda item: (-item.score, item.recipe_id))


def satisfies_hard_filters(
    recipe: Recipe,
    required_ingredients: Sequence[str],
    excluded_ingredients: Sequence[str],
    constraints: QueryConstraints,
) -> bool:
    ingredient_names = {ingredient.name.casefold() for ingredient in recipe.ingredients}
    searchable = ingredient_names | {recipe.name.casefold()}

    def matches(item: str) -> bool:
        candidates = _INGREDIENT_EQUIVALENTS.get(item, (item,))
        return any(
            candidate.casefold() in value for candidate in candidates for value in searchable
        )

    if any(not recipe_has_label(recipe, label) for label in constraints.required_labels):
        return False
    if any(recipe_has_label(recipe, label) for label in constraints.excluded_labels):
        return False
    if any(not matches(item) for item in required_ingredients):
        return False
    if any(matches(item) for item in excluded_ingredients):
        return False
    if constraints.max_minutes is not None and (
        recipe.duration_minutes is None or recipe.duration_minutes > constraints.max_minutes
    ):
        return False
    if constraints.categories:
        category_values = {value.casefold() for value in recipe.categories}
        source_path = recipe.source_path.casefold()
        if not any(
            value.casefold() in category_values or f"/{value.casefold()}/" in f"/{source_path}"
            for value in constraints.categories
        ):
            return False
    recipe_search = recipe.name.casefold() + " " + " ".join(recipe.tools).casefold()
    if constraints.tools and any(
        tool.casefold() not in recipe_search for tool in constraints.tools
    ):
        return False
    if constraints.excluded_tools and any(
        tool.casefold() in recipe_search for tool in constraints.excluded_tools
    ):
        return False
    return not (
        constraints.difficulties
        and (recipe.difficulty is None or recipe.difficulty not in constraints.difficulties)
    )
