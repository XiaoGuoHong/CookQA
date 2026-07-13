from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from cookqa.models import QueryConstraints, Recipe


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
    if any(item.casefold() not in ingredient_names for item in required_ingredients):
        return False
    if any(item.casefold() in ingredient_names for item in excluded_ingredients):
        return False
    if constraints.max_minutes is not None and (
        recipe.duration_minutes is None or recipe.duration_minutes > constraints.max_minutes
    ):
        return False
    if constraints.categories and (
        not recipe.categories or not set(constraints.categories).intersection(recipe.categories)
    ):
        return False
    if constraints.tools and (
        not recipe.tools or not set(constraints.tools).issubset(recipe.tools)
    ):
        return False
    return not (
        constraints.difficulties
        and (recipe.difficulty is None or recipe.difficulty not in constraints.difficulties)
    )
