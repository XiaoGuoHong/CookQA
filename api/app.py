from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from cookqa import __version__
from cookqa.config import Settings
from cookqa.ingest.normalize import normalize_ingredient
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


class PantrySearchRequest(BaseModel):
    existing_ingredients: list[str] = Field(min_length=1, max_length=30)
    excluded_ingredients: list[str] = Field(default_factory=list, max_length=30)
    max_minutes: int | None = Field(default=None, ge=1, le=1440)
    no_spicy: bool = False
    use_pantry_staples: bool = True

    @field_validator("existing_ingredients", "excluded_ingredients")
    @classmethod
    def normalize_ingredient_inputs(cls, values: list[str]) -> list[str]:
        cleaned = []
        for value in values:
            value = value.strip()
            if not 1 <= len(value) <= 50:
                raise ValueError("食材名称长度必须为 1-50 个字符")
            cleaned.append(value)
        return cleaned


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
    pantry_matcher: Any | None = None,
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

    @application.post("/api/v1/pantry/search")
    async def pantry_search(body: PantrySearchRequest):
        matcher = pantry_matcher or getattr(service, "pantry_matcher", None)
        if matcher is None:
            raise HTTPException(status_code=503, detail="食材匹配服务不可用")
        aliases = getattr(matcher, "aliases", {})
        existing = [normalize_ingredient(item, aliases) for item in body.existing_ingredients]
        excluded = [normalize_ingredient(item, aliases) for item in body.excluded_ingredients]
        if not any(existing) or set(existing).intersection(excluded):
            raise HTTPException(status_code=422, detail="已有食材与排除食材不能冲突")
        try:
            return matcher.match(
                body.existing_ingredients,
                body.excluded_ingredients,
                max_minutes=body.max_minutes,
                no_spicy=body.no_spicy,
                use_staples=body.use_pantry_staples,
            )
        except RuntimeError as exc:
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
