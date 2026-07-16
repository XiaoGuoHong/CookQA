from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from time import perf_counter

from cookqa.ingest.normalize import normalize_ingredient
from cookqa.models import PantryMatch, PantrySearchResponse, Recipe


class PantryMatcher:
    def __init__(
        self, recipes: Iterable[Recipe], aliases: Mapping[str, str], staples: Iterable[str] = ()
    ) -> None:
        self.recipes = tuple(recipes)
        self.aliases = dict(aliases)
        self.staples = {normalize_ingredient(item, self.aliases) for item in staples}
        self.known_ingredients = {
            item.name for recipe in self.recipes for item in recipe.ingredients
        }

    @classmethod
    def from_files(
        cls, recipes: Iterable[Recipe], aliases: Mapping[str, str], staples_path: Path | None = None
    ):
        path = (
            staples_path or Path(__file__).resolve().parents[1] / "config" / "pantry_staples.json"
        )
        staples = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(staples, list) or not all(isinstance(item, str) for item in staples):
            raise ValueError("pantry_staples.json 必须是字符串数组")
        return cls(recipes, aliases, staples)

    def _normalize(self, values: Iterable[str]) -> tuple[list[str], list[str]]:
        normalized, unknown = [], []
        for raw in values:
            value = normalize_ingredient(raw, self.aliases)
            if value and value not in normalized:
                normalized.append(value)
                if value not in self.known_ingredients:
                    unknown.append(raw.strip())
        return normalized, unknown

    @staticmethod
    def _is_spicy(recipe: Recipe) -> bool:
        tokens = ("辣", "辣椒", "小米椒", "豆瓣酱")
        text = " ".join([*recipe.tags, *(item.name for item in recipe.ingredients)])
        return any(token in text for token in tokens)

    def match(
        self,
        existing: Iterable[str],
        excluded: Iterable[str],
        *,
        max_minutes: int | None = None,
        no_spicy: bool = False,
        use_staples: bool = True,
    ) -> PantrySearchResponse:
        started = perf_counter()
        normalized_existing, existing_unknown = self._normalize(existing)
        normalized_excluded, excluded_unknown = self._normalize(excluded)
        existing_set, excluded_set = set(normalized_existing), set(normalized_excluded)
        warnings = (
            ["部分输入未识别，已按可识别食材继续匹配"]
            if existing_unknown or excluded_unknown
            else []
        )
        groups: dict[str, list[PantryMatch]] = {"ready": [], "near": [], "related": []}
        for recipe in self.recipes:
            names = [item.name for item in recipe.ingredients]
            if excluded_set.intersection(names):
                continue
            if max_minutes is not None and (
                recipe.duration_minutes is None or recipe.duration_minutes > max_minutes
            ):
                continue
            if no_spicy and self._is_spicy(recipe):
                continue
            required = [item.name for item in recipe.ingredients if not item.optional]
            optional = [item.name for item in recipe.ingredients if item.optional]
            staples = [item for item in required if use_staples and item in self.staples]
            available_set = existing_set | set(staples)
            missing = [item for item in required if item not in available_set]
            matched = [item for item in required if item in available_set]
            coverage = len(matched) / len(required) if required else 1.0
            if not missing:
                group = "ready"
            elif len(missing) <= 2:
                group = "near"
            elif coverage >= 0.5:
                group = "related"
            else:
                continue
            groups[group].append(
                PantryMatch(
                    recipe=recipe,
                    group=group,
                    coverage=coverage,
                    available_ingredients=[item for item in names if item in available_set],
                    missing_ingredients=missing,
                    optional_ingredients=optional,
                    staple_ingredients=staples,
                    reasons=[
                        f"已匹配 {len(matched)} 种必需食材",
                        f"缺少 {len(missing)} 种必需食材",
                    ],
                )
            )
        for items in groups.values():
            items.sort(
                key=lambda item: (
                    len(item.missing_ingredients),
                    -item.coverage,
                    -len(item.available_ingredients),
                    item.recipe.name,
                )
            )
        return PantrySearchResponse(
            normalized_existing=normalized_existing,
            normalized_excluded=normalized_excluded,
            ready=groups["ready"][:5],
            near=groups["near"][:5],
            related=groups["related"][:5],
            warnings=warnings,
            timings_ms={"match": (perf_counter() - started) * 1000},
        )
