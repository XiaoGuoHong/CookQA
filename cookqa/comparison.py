from __future__ import annotations

from cookqa.models import Recipe, RecipeComparison, ScalarComparison, SetComparison

UNKNOWN = "无法确认"


def _compare_sets(left: list[str], right: list[str]) -> SetComparison:
    if not left or not right:
        return SetComparison(
            left=UNKNOWN,
            right=UNKNOWN,
            common=UNKNOWN,
            only_left=UNKNOWN,
            only_right=UNKNOWN,
        )
    left_values = sorted(set(left))
    right_values = sorted(set(right))
    left_set = set(left_values)
    right_set = set(right_values)
    return SetComparison(
        left=left_values,
        right=right_values,
        common=sorted(left_set & right_set),
        only_left=sorted(left_set - right_set),
        only_right=sorted(right_set - left_set),
    )


def _compare_scalars(left: str | int | None, right: str | int | None) -> ScalarComparison:
    left_value = left if left is not None and left != "" else UNKNOWN
    right_value = right if right is not None and right != "" else UNKNOWN
    if UNKNOWN in (left_value, right_value):
        relationship = "unknown"
    elif left_value == right_value:
        relationship = "same"
    else:
        relationship = "different"
    return ScalarComparison(
        left=left_value,
        right=right_value,
        relationship=relationship,
    )


class RecipeComparator:
    @staticmethod
    def compare(left: Recipe, right: Recipe) -> RecipeComparison:
        return RecipeComparison(
            left_recipe_id=left.recipe_id,
            right_recipe_id=right.recipe_id,
            ingredients=_compare_sets(
                [ingredient.name for ingredient in left.ingredients],
                [ingredient.name for ingredient in right.ingredients],
            ),
            categories=_compare_sets(left.categories, right.categories),
            methods=_compare_sets(left.methods, right.methods),
            tools=_compare_sets(left.tools, right.tools),
            difficulty=_compare_scalars(left.difficulty, right.difficulty),
            duration_minutes=_compare_scalars(
                left.duration_minutes,
                right.duration_minutes,
            ),
        )
