from pathlib import Path
import sys

from fastapi import FastAPI, HTTPException, Query

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cookqa import __version__
from cookqa.config import CookQASettings
from cookqa.ollama_client import OllamaClient
from cookqa.service import CookQAService

from .schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    RebuildResponse,
    SearchResponse,
)


_DEFAULT_OLLAMA = object()


def create_app(
    settings: CookQASettings | None = None,
    ollama_client: OllamaClient | None | object = _DEFAULT_OLLAMA,
) -> FastAPI:
    settings = settings or CookQASettings.from_env()
    if ollama_client is _DEFAULT_OLLAMA:
        service = CookQAService.from_settings(settings)
    else:
        service = CookQAService.from_settings(settings, ollama_client=ollama_client)

    app = FastAPI(
        title="CookQA API",
        description="食神 CookQA 食谱 GraphRAG API",
        version=__version__,
    )
    app.state.cookqa_service = service
    app.state.cookqa_settings = settings

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="CookQA", version=__version__)

    @app.post("/api/v1/chat", response_model=ChatResponse, tags=["cookqa"])
    def chat(request: ChatRequest) -> ChatResponse:
        result = app.state.cookqa_service.chat(
            request.question,
            top_k=request.top_k,
            include_steps=request.include_steps,
        )
        return ChatResponse(**result.model_dump())

    @app.get("/api/v1/recipes/search", response_model=SearchResponse, tags=["cookqa"])
    def search(
        q: str = Query(..., min_length=1),
        top_k: int = Query(5, ge=1, le=20),
    ) -> SearchResponse:
        mode, recommendations = app.state.cookqa_service.search(q.strip(), top_k=top_k)
        return SearchResponse(mode=mode, recommendations=recommendations)

    @app.get("/api/v1/recipes/{recipe_id:path}", tags=["cookqa"])
    def recipe_detail(recipe_id: str):
        try:
            return app.state.cookqa_service.get_recipe(recipe_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="recipe not found") from exc

    @app.post("/api/v1/index/rebuild", response_model=RebuildResponse, tags=["cookqa"])
    def rebuild(vectors: bool = Query(False)) -> RebuildResponse:
        if not app.state.cookqa_settings.enable_rebuild_api:
            raise HTTPException(status_code=403, detail="index rebuild API is disabled")
        if vectors:
            result = app.state.cookqa_service.rebuild_indexes()
        else:
            result = app.state.cookqa_service.rebuild_metadata()
        return RebuildResponse(status="ok", result=result)

    return app


app = create_app()
