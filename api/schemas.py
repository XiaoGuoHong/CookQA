from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator

from cookqa.models import QueryMode, Recommendation, SourceRef


class ChatRequest(BaseModel):
    question: str = Field(..., examples=["牛肉可以怎么做"])
    top_k: int = Field(5, ge=1, le=20)
    include_steps: bool = True

    @field_validator("question")
    @classmethod
    def question_must_not_be_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question cannot be empty")
        return stripped


class ChatResponse(BaseModel):
    answer: str
    mode: QueryMode
    recommendations: List[Recommendation]
    sources: List[SourceRef]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    mode: QueryMode
    recommendations: List[Recommendation]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class RebuildResponse(BaseModel):
    status: str
    result: Dict[str, int]
