# CookQA Graph RAG MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the confirmed Windows-local CookQA Graph RAG MVP with deterministic routing, BM25/FAISS/Neo4j retrieval, Ollama generation, FastAPI endpoints, and a static Web UI.

**Architecture:** Use a small ports-and-adapters package: deterministic domain services depend on retrieval/generation protocols, while Neo4j, FAISS, BM25, and Ollama live behind adapters. All indexes are built from one normalized `recipes.jsonl` and validated by one version manifest before the API reports ready.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, Uvicorn, Neo4j Python driver, FAISS CPU, rank-bm25, jieba, NumPy, HTTPX, pytest, static HTML/CSS/JavaScript, local Ollama (`qwen3.5:4b`, `bge-m3`).

## Global Constraints

- Windows-local only; no Docker and no cloud API.
- Bind the application to `127.0.0.1` by default.
- Read Neo4j credentials only from environment variables and never log secrets or authorization headers.
- Retrieval routing is deterministic; the LLM does not generate Cypher, choose retrieval weights, or enter the search critical path.
- Build only recipe-level indexes; recipe steps remain structured detail fields.
- Search and generation stay on separate endpoints.
- Missing hard-filter data is not treated as satisfying the filter.
- Runtime data under `Data/` is ignored by Git; only selection manifests, parsing rules, sample configuration, and build code are versioned.

---

### Task 1: Package Skeleton, Configuration, and Domain Models

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `cookqa/__init__.py`
- Create: `cookqa/config.py`
- Create: `cookqa/models.py`
- Test: `tests/test_config.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: environment variables only.
- Produces: `Settings.from_env()`, `Recipe`, `Ingredient`, `QueryPlan`, `SearchResult`, `SearchResponse`, `ReadinessReport`.

- [ ] **Step 1: Write failing configuration and model tests**

```python
def test_settings_use_local_safe_defaults(monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    settings = Settings.from_env()
    assert settings.host == "127.0.0.1"
    assert settings.chat_model == "qwen3.5:4b"
    assert settings.embedding_model == "bge-m3"
    assert settings.neo4j_password is None


def test_recipe_rejects_duplicate_ingredient_names():
    with pytest.raises(ValueError):
        Recipe(recipe_id="r1", name="测试菜", ingredients=[
            Ingredient(name="鸡蛋", raw="鸡蛋 1 个"),
            Ingredient(name="鸡蛋", raw="鸡蛋 2 个"),
        ], source_path="dishes/test.md", source_version="abc")
```

- [ ] **Step 2: Run the tests and verify missing-package failures**

Run: `python -m pytest tests/test_config.py tests/test_models.py -q`

Expected: FAIL because `cookqa.config` and `cookqa.models` do not exist.

- [ ] **Step 3: Implement the minimal settings and Pydantic models**

```python
@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    chat_model: str = "qwen3.5:4b"
    embedding_model: str = "bge-m3"
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None

    @classmethod
    def from_env(cls) -> "Settings": ...


class Recipe(BaseModel):
    recipe_id: str
    name: str
    aliases: list[str] = []
    categories: list[str] = []
    ingredients: list[Ingredient]
    steps: list[str] = []
    source_path: str
    source_version: str

    @model_validator(mode="after")
    def ingredients_are_unique(self) -> "Recipe": ...
```

- [ ] **Step 4: Run the focused tests**

Run: `python -m pytest tests/test_config.py tests/test_models.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore .env.example cookqa tests/test_config.py tests/test_models.py
git commit -m "chore: initialize CookQA domain package"
```

### Task 2: Deterministic HowToCook Parsing and Normalization

**Files:**
- Create: `cookqa/ingest/__init__.py`
- Create: `cookqa/ingest/normalize.py`
- Create: `cookqa/ingest/parser.py`
- Create: `cookqa/ingest/selection.py`
- Create: `config/ingredient_aliases.json`
- Create: `config/recipe-selection.txt`
- Test: `tests/fixtures/howtocook/sample.md`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: UTF-8 HowToCook Markdown and repository-relative paths.
- Produces: `stable_recipe_id(relative_path) -> str`, `parse_recipe(path, source_root, source_version, aliases) -> Recipe`, `load_selection(path) -> list[str]`.

- [ ] **Step 1: Write failing parser tests**

```python
def test_recipe_id_is_stable_for_normalized_relative_path():
    assert stable_recipe_id("dishes/meat/宫保鸡丁.md") == stable_recipe_id(
        "dishes\\meat\\宫保鸡丁.md"
    )


def test_parser_preserves_raw_ingredient_and_normalizes_alias(tmp_path):
    recipe = parse_recipe(
        SAMPLE,
        source_root=SAMPLE.parent,
        source_version="abc123",
        aliases={"西红柿": "番茄"},
    )
    assert recipe.name == "番茄炒蛋"
    assert recipe.ingredients[0].name == "番茄"
    assert "西红柿" in recipe.ingredients[0].raw
    assert recipe.source_version == "abc123"
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_ingest.py -q`

Expected: FAIL because the ingest package is missing.

- [ ] **Step 3: Implement deterministic parsing**

```python
def stable_recipe_id(relative_path: str) -> str:
    normalized = PurePosixPath(relative_path.replace("\\", "/")).as_posix().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def normalize_ingredient(raw_name: str, aliases: Mapping[str, str]) -> str:
    value = re.sub(r"[\s　]+", "", raw_name)
    return aliases.get(value, value)
```

The parser must fail with a path-specific `RecipeParseError` when name, ingredients, or steps cannot be extracted; it must never silently skip a selected recipe.

- [ ] **Step 4: Run parser tests**

Run: `python -m pytest tests/test_ingest.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cookqa/ingest config tests/fixtures tests/test_ingest.py
git commit -m "feat: add deterministic recipe ingestion"
```

### Task 3: Deterministic Query Router

**Files:**
- Create: `cookqa/query/__init__.py`
- Create: `cookqa/query/router.py`
- Test: `tests/test_router.py`

**Interfaces:**
- Consumes: normalized recipe-name and ingredient dictionaries.
- Produces: `QueryRouter.route(query: str) -> QueryPlan` with intent, recognized recipes, required/excluded ingredients, constraints, strategy, confidence, and optional clarification.

- [ ] **Step 1: Write one failing test per documented intent**

```python
@pytest.mark.parametrize(("query", "intent"), [
    ("宫保鸡丁怎么做", "exact_recipe"),
    ("鸡蛋和番茄能做什么", "ingredient_lookup"),
    ("推荐20分钟内不辣的鸡肉菜", "conditional_recommendation"),
    ("想吃清淡又下饭的菜", "semantic_recommendation"),
    ("找和鱼香肉丝相似但不含猪肉的菜", "similar_recipe"),
    ("宫保鸡丁和辣子鸡有什么区别", "recipe_comparison"),
])
def test_routes_supported_intents(router, query, intent):
    assert router.route(query).intent == intent


def test_step_question_without_recipe_requests_clarification(router):
    plan = router.route("鸡蛋什么时候下锅")
    assert plan.intent == "clarification_required"
    assert plan.clarification
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_router.py -q`

Expected: FAIL because `QueryRouter` is missing.

- [ ] **Step 3: Implement ordered, explainable routing rules**

```python
class QueryRouter:
    def route(self, query: str) -> QueryPlan:
        normalized = normalize_query(query)
        if not normalized:
            raise ValueError("查询不能为空")
        if self._is_comparison(normalized): ...
        if self._is_similarity(normalized): ...
        if self._is_step_question(normalized) and not recognized_recipes: ...
        if recognized_recipes: ...
        if constraints: ...
        if required_ingredients: ...
        return self._semantic_plan(normalized)
```

- [ ] **Step 4: Run router tests**

Run: `python -m pytest tests/test_router.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cookqa/query tests/test_router.py
git commit -m "feat: add deterministic query routing"
```

### Task 4: Retrieval Ports, RRF, Hard Filters, and Degradation

**Files:**
- Create: `cookqa/retrieval/__init__.py`
- Create: `cookqa/retrieval/ports.py`
- Create: `cookqa/retrieval/bm25.py`
- Create: `cookqa/retrieval/faiss_store.py`
- Create: `cookqa/retrieval/neo4j_store.py`
- Create: `cookqa/retrieval/fusion.py`
- Create: `cookqa/retrieval/coordinator.py`
- Test: `tests/test_bm25.py`
- Test: `tests/test_faiss_store.py`
- Test: `tests/test_fusion.py`
- Test: `tests/test_coordinator.py`
- Test: `tests/test_neo4j_queries.py`

**Interfaces:**
- Consumes: `QueryPlan`, recipe corpus, embeddings, and parameterized Neo4j sessions.
- Produces: `RankedCandidate`, `RetrievalOutcome`, `RetrievalCoordinator.search(plan, limit=5)`.

- [ ] **Step 1: Write failing RRF and hard-filter tests**

```python
def test_rrf_fuses_by_rank_not_raw_score():
    fused = reciprocal_rank_fusion({
        "bm25": ["a", "b"],
        "faiss": ["b", "a"],
        "graph": ["b"],
    }, weights={"bm25": 1.0, "faiss": 1.0, "graph": 1.0})
    assert fused[0].recipe_id == "b"


def test_missing_duration_does_not_pass_max_duration_filter():
    assert not satisfies_hard_filters(recipe_without_duration, {"max_minutes": 20})
```

- [ ] **Step 2: Write failing degradation tests**

```python
@pytest.mark.asyncio
async def test_graph_failure_with_hard_filter_marks_results_unverified():
    outcome = await coordinator_with_failed_graph.search(hard_filter_plan)
    assert "neo4j" in outcome.unavailable_components
    assert outcome.constraints_verified is False
    assert outcome.warnings
```

- [ ] **Step 3: Verify RED**

Run: `python -m pytest tests/test_bm25.py tests/test_faiss_store.py tests/test_fusion.py tests/test_coordinator.py tests/test_neo4j_queries.py -q`

Expected: FAIL because retrieval modules are missing.

- [ ] **Step 4: Implement ports and minimal adapters**

```python
class RankedRetriever(Protocol):
    name: str
    async def search(self, plan: QueryPlan, limit: int) -> list[RankedCandidate]: ...


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[str]],
    weights: Mapping[str, float],
    k: int = 60,
) -> list[FusedCandidate]: ...
```

Neo4j queries must use `$required_ingredients`, `$excluded_ingredients`, and other parameters; never interpolate user text into Cypher.

- [ ] **Step 5: Implement concurrent coordination and explicit fallback metadata**

```python
results = await asyncio.gather(
    *(run_retriever(retriever, plan) for retriever in selected),
    return_exceptions=True,
)
```

If no retriever succeeds, raise `RetrievalUnavailable`. If Neo4j fails while hard conditions exist, return candidates only with `constraints_verified=False` and an explicit warning.

- [ ] **Step 6: Run retrieval tests**

Run: `python -m pytest tests/test_bm25.py tests/test_faiss_store.py tests/test_fusion.py tests/test_coordinator.py tests/test_neo4j_queries.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add cookqa/retrieval tests/test_bm25.py tests/test_faiss_store.py tests/test_fusion.py tests/test_coordinator.py tests/test_neo4j_queries.py
git commit -m "feat: add hybrid retrieval and safe degradation"
```

### Task 5: Build Pipeline and Cross-Index Manifest Validation

**Files:**
- Create: `cookqa/indexing/__init__.py`
- Create: `cookqa/indexing/manifest.py`
- Create: `cookqa/indexing/builder.py`
- Create: `cookqa/cli.py`
- Test: `tests/test_manifest.py`
- Test: `tests/test_builder.py`

**Interfaces:**
- Consumes: selection list, HowToCook source root, alias map, Neo4j connection, and Ollama embeddings.
- Produces: `Data/processed/recipes.jsonl`, `Data/indexes/<version>/`, Neo4j graph data, and `index-manifest.json`.

- [ ] **Step 1: Write failing consistency tests**

```python
def test_manifest_rejects_mixed_recipe_ids():
    with pytest.raises(ManifestMismatch):
        validate_manifest(manifest, bm25_ids={"a"}, faiss_ids={"a", "b"}, graph_ids={"a"})


def test_id_hash_is_order_independent():
    assert compute_id_hash(["b", "a"]) == compute_id_hash(["a", "b"])
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_manifest.py tests/test_builder.py -q`

Expected: FAIL because indexing modules are missing.

- [ ] **Step 3: Implement staged build and atomic activation**

```python
@dataclass(frozen=True)
class IndexManifest:
    data_version: str
    recipe_count: int
    recipe_id_hash: str
    embedding_model: str
    embedding_dimension: int
    bm25_version: str
    faiss_version: str
    graph_version: str
```

Build into `Data/runtime/builds/<uuid>/`, validate every selected file and every index ID set, write the manifest, then replace the active-version pointer. On failure, write a redacted report and leave the prior active version untouched.

- [ ] **Step 4: Run build tests**

Run: `python -m pytest tests/test_manifest.py tests/test_builder.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cookqa/indexing cookqa/cli.py tests/test_manifest.py tests/test_builder.py
git commit -m "feat: add reproducible index build pipeline"
```

### Task 6: Search Service, FastAPI, Readiness, and Ollama Streaming

**Files:**
- Create: `cookqa/service.py`
- Create: `cookqa/generation/__init__.py`
- Create: `cookqa/generation/ollama.py`
- Create: `api/__init__.py`
- Create: `api/app.py`
- Test: `tests/test_service.py`
- Test: `tests/test_api.py`
- Test: `tests/test_ollama.py`

**Interfaces:**
- Consumes: router, retrieval coordinator, recipe store, manifest validator, Neo4j health probe, and Ollama HTTP client.
- Produces: `POST /api/v1/search`, `GET /api/v1/recipes/{recipe_id}`, `POST /api/v1/recipes/{recipe_id}/answer/stream`, `GET /health`, `GET /ready`.

- [ ] **Step 1: Write failing endpoint tests**

```python
def test_search_rejects_blank_query(client):
    response = client.post("/api/v1/search", json={"query": "   "})
    assert response.status_code == 422


def test_recipe_detail_does_not_call_generator(client, generator):
    response = client.get("/api/v1/recipes/r1")
    assert response.status_code == 200
    generator.stream.assert_not_called()


def test_ready_reports_manifest_mismatch(unready_client):
    response = unready_client.get("/ready")
    assert response.status_code == 503
    assert response.json()["ready"] is False
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_service.py tests/test_api.py tests/test_ollama.py -q`

Expected: FAIL because service/API modules are missing.

- [ ] **Step 3: Implement application services and dependency injection**

```python
@app.post("/api/v1/search", response_model=SearchResponse)
async def search(request: SearchRequest, service: SearchService = Depends(get_service)):
    return await service.search(request.query)


@app.get("/api/v1/recipes/{recipe_id}", response_model=Recipe)
async def recipe_detail(recipe_id: str, service: SearchService = Depends(get_service)):
    recipe = service.get_recipe(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="菜谱不存在")
    return recipe
```

- [ ] **Step 4: Implement streaming with client cancellation**

```python
async def event_stream(request: Request):
    async for chunk in generator.stream(recipe, body.question):
        if await request.is_disconnected():
            break
        yield chunk
```

The Ollama prompt contains only structured recipe fields and the optional user question. HTTP errors must not expose request headers or credentials.

- [ ] **Step 5: Run API tests**

Run: `python -m pytest tests/test_service.py tests/test_api.py tests/test_ollama.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add cookqa/service.py cookqa/generation api tests/test_service.py tests/test_api.py tests/test_ollama.py
git commit -m "feat: expose search detail and streaming APIs"
```

### Task 7: Static Web UI

**Files:**
- Create: `web/index.html`
- Create: `web/styles.css`
- Create: `web/app.js`
- Modify: `api/app.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: the three API endpoints from Task 6.
- Produces: browser UI at `/` and assets under `/static/`.

- [ ] **Step 1: Write failing static-resource tests**

```python
def test_homepage_and_static_assets_are_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


def test_homepage_has_accessible_search_controls(client):
    html = client.get("/").text
    assert 'id="query-input"' in html
    assert 'aria-live="polite"' in html
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_web.py -q`

Expected: FAIL because the UI is missing.

- [ ] **Step 3: Implement the minimal UI state flow**

```javascript
async function searchRecipes(query) {
  const response = await fetch('/api/v1/search', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({query})
  });
  if (!response.ok) throw new Error('搜索失败，请稍后重试');
  return response.json();
}
```

Render Top 5 cards with category, difficulty, duration, primary ingredients, reasons, source, inferred-field badges, retrieval strategy, and degradation warnings. Clicking a card immediately fetches structured detail; generation starts only when the user presses the answer button.

- [ ] **Step 4: Run UI tests**

Run: `python -m pytest tests/test_web.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web api/app.py tests/test_web.py
git commit -m "feat: add CookQA browser interface"
```

### Task 8: Fixed Evaluation Set, Benchmarks, Documentation, and Final Verification

**Files:**
- Create: `evaluation/queries.jsonl`
- Create: `scripts/benchmark.py`
- Create: `README.md`
- Create: `scripts/start.ps1`
- Create: `scripts/build-indexes.ps1`
- Test: `tests/test_evaluation_dataset.py`

**Interfaces:**
- Consumes: active local indexes and API.
- Produces: at least 50 fixed queries across six intents, Recall@5 and hard-filter reports, warmed P95 search/first-token timings, and exact Windows setup commands.

- [ ] **Step 1: Write failing evaluation-schema tests**

```python
def test_evaluation_set_has_required_coverage():
    cases = load_cases(Path("evaluation/queries.jsonl"))
    assert len(cases) >= 50
    assert {case.intent for case in cases} == {
        "exact_recipe", "ingredient_lookup", "conditional_recommendation",
        "semantic_recommendation", "similar_recipe", "recipe_comparison",
    }
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_evaluation_dataset.py -q`

Expected: FAIL because the evaluation set is missing.

- [ ] **Step 3: Add 50 concrete cases and benchmark reporting**

```python
report = {
    "recall_at_5": hits / len(cases),
    "hard_filter_violations": violations,
    "search_p95_ms": percentile(search_samples, 95),
    "first_token_p95_ms": percentile(first_token_samples, 95),
    "cold_start_ms": cold_start_ms,
}
```

Do not claim performance targets passed unless the benchmark ran against the current machine with warmed Ollama and Neo4j.

- [ ] **Step 4: Document local setup without secrets**

Document Python environment creation, dependency installation, HowToCook checkout location, selection/build commands, Neo4j ZIP setup, required environment variable names with placeholders, Ollama model pulls, index build, startup, tests, and benchmark commands.

- [ ] **Step 5: Run the complete suite**

Run: `$env:TEMP="$PWD\.tmp\pytest-temp"; $env:TMP=$env:TEMP; New-Item -ItemType Directory -Force $env:TEMP | Out-Null; python -m pytest -q --basetemp .tmp\pytest-run -o cache_dir=.tmp\pytest-cache`

Expected: all tests PASS with no leaked secrets or unexpected warnings.

- [ ] **Step 6: Run static checks**

Run: `python -m ruff check .`

Expected: PASS.

- [ ] **Step 7: Run a local smoke test when dependencies are available**

Run: `python -m uvicorn api.app:app --host 127.0.0.1 --port 8010`

Expected: `/health` returns 200; `/ready` truthfully returns 200 only with consistent indexes, Neo4j, and Ollama, otherwise 503 with component status.

- [ ] **Step 8: Commit**

```bash
git add evaluation scripts README.md tests/test_evaluation_dataset.py
git commit -m "docs: add local operations and evaluation workflow"
```

