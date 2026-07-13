from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from cookqa import __version__
from cookqa.config import Settings
from cookqa.retrieval.coordinator import RetrievalUnavailable
from cookqa.runtime import build_runtime


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)

    @field_validator("query")
    @classmethod
    def query_is_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("查询不能为空")
        return value


class AnswerRequest(BaseModel):
    question: str | None = Field(default=None, max_length=500)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


def create_app(
    service: Any,
    readiness: Any,
    generator: Any,
    *,
    mount_web: bool = True,
) -> FastAPI:
    application = FastAPI(title="CookQA", version=__version__)

    @application.get("/health")
    async def health():
        return {"status": "ok", "service": "CookQA", "version": __version__}

    @application.get("/ready")
    async def ready():
        report = await readiness.check()
        if not report.ready:
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=503, content=report.model_dump())
        return report

    @application.post("/api/v1/search")
    async def search(body: SearchRequest):
        try:
            return await service.search(body.query)
        except (RetrievalUnavailable, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.get("/api/v1/recipes/{recipe_id}")
    async def recipe_detail(recipe_id: str):
        recipe = service.get_recipe(recipe_id)
        if recipe is None:
            raise HTTPException(status_code=404, detail="菜谱不存在")
        return recipe

    @application.post("/api/v1/recipes/{recipe_id}/answer/stream")
    async def answer_stream(recipe_id: str, body: AnswerRequest, request: Request):
        recipe = service.get_recipe(recipe_id)
        if recipe is None:
            raise HTTPException(status_code=404, detail="菜谱不存在")

        async def chunks():
            async for chunk in generator.stream(recipe, body.question):
                if await request.is_disconnected():
                    break
                yield chunk

        return StreamingResponse(chunks(), media_type="text/plain; charset=utf-8")

    web_dir = Path(__file__).resolve().parents[1] / "web"
    if mount_web and web_dir.is_dir():
        application.mount("/static", StaticFiles(directory=web_dir), name="static")

        @application.get("/", include_in_schema=False)
        async def homepage():
            return FileResponse(web_dir / "index.html")

    return application


_settings = Settings.from_env()
_service, _readiness, _generator = build_runtime(_settings)
app = create_app(_service, _readiness, _generator)
