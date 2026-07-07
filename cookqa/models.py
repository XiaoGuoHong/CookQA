from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


QueryMode = Literal[
    "dish_lookup",
    "ingredient_exploration",
    "missing_or_fictional",
    "general",
]


class RecipeDocument(BaseModel):
    recipe_id: str
    name: str
    category: str
    source_path: str
    source_url: Optional[str] = None
    description: str = ""
    difficulty: Optional[str] = None
    calories: Optional[str] = None
    ingredients: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    raw_text: str = ""

    def search_text(self) -> str:
        parts = [
            self.name,
            self.category,
            self.description,
            " ".join(self.ingredients),
            " ".join(self.tools),
            " ".join(self.steps),
            " ".join(self.notes),
        ]
        return "\n".join(part for part in parts if part).strip()

    def summary_steps(self, limit: int = 5) -> List[str]:
        return self.steps[:limit]


class RecipeChunk(BaseModel):
    chunk_id: str
    recipe_id: str
    name: str
    source_path: str
    text: str
    kind: Literal["recipe", "step"]
    ordinal: int = 0


class Recommendation(BaseModel):
    recipe_id: str
    name: str
    score: float
    match_reason: str
    ingredients: List[str] = Field(default_factory=list)
    summary_steps: List[str] = Field(default_factory=list)
    source_path: str
    source_url: Optional[str] = None
    graph_matches: List[str] = Field(default_factory=list)


class SourceRef(BaseModel):
    recipe_id: str
    name: str
    source_path: str
    source_url: Optional[str] = None


class ChatResult(BaseModel):
    answer: str
    mode: QueryMode
    recommendations: List[Recommendation]
    sources: List[SourceRef]
    metadata: Dict[str, Any] = Field(default_factory=dict)
