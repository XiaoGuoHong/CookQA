from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Intent = Literal[
    "exact_recipe",
    "ingredient_lookup",
    "conditional_recommendation",
    "semantic_recommendation",
    "similar_recipe",
    "recipe_comparison",
    "clarification_required",
]


class Ingredient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    raw: str = Field(min_length=1)
    amount: float | None = None
    unit: str | None = None
    optional: bool = False

    @field_validator("name", "raw")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("字段不能为空")
        return value


class FieldEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    source: Literal["source", "rule"]
    confidence: float = Field(ge=0, le=1)
    basis: str | None = None


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    summary: str | None = None
    ingredients: list[Ingredient] = Field(min_length=1)
    difficulty: str | None = None
    calories: float | None = Field(default=None, ge=0)
    duration_minutes: int | None = Field(default=None, ge=0)
    methods: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    evidence: list[FieldEvidence] = Field(default_factory=list)
    source_path: str = Field(min_length=1)
    source_version: str = Field(min_length=1)

    @field_validator("recipe_id", "name", "source_path", "source_version")
    @classmethod
    def strip_recipe_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("字段不能为空")
        return value

    @model_validator(mode="after")
    def ingredients_are_unique(self) -> "Recipe":
        names = [item.name.casefold() for item in self.ingredients]
        if len(names) != len(set(names)):
            raise ValueError("规范化食材名称不能重复")
        return self


class QueryConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_minutes: int | None = Field(default=None, gt=0)
    categories: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    difficulties: list[str] = Field(default_factory=list)
    subjective_tags: list[str] = Field(default_factory=list)

    def has_hard_filters(self) -> bool:
        return bool(
            self.max_minutes is not None
            or self.categories
            or self.tools
            or self.difficulties
        )


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_query: str
    normalized_query: str
    intent: Intent
    recognized_recipes: list[str] = Field(default_factory=list)
    required_ingredients: list[str] = Field(default_factory=list)
    excluded_ingredients: list[str] = Field(default_factory=list)
    constraints: QueryConstraints = Field(default_factory=QueryConstraints)
    retrieval_strategy: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    clarification: str | None = None


class RankedCandidate(BaseModel):
    recipe_id: str
    score: float
    source: str
    reasons: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    recipe: Recipe
    score: float
    reasons: list[str] = Field(default_factory=list)
    retrieval_sources: list[str] = Field(default_factory=list)
    constraints_verified: bool = True


class DegradationStatus(BaseModel):
    degraded: bool = False
    unavailable_components: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query_plan: QueryPlan
    results: list[SearchResult] = Field(default_factory=list)
    retrieval_strategy: list[str] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    degradation: DegradationStatus = Field(default_factory=DegradationStatus)


class ComponentStatus(BaseModel):
    available: bool
    detail: str | None = None


class ReadinessReport(BaseModel):
    ready: bool
    components: dict[str, ComponentStatus]
    manifest: dict[str, Any] | None = None
