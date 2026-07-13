# CookQA Structured Recipe Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return exactly the two recognized recipes and a deterministic structured comparison instead of unrelated Top 5 candidates.

**Architecture:** Add explicit comparison response models and a pure `RecipeComparator` over the active version's structured Recipe objects. `SearchService` routes `recipe_comparison` directly to the comparator and never invokes BM25, FAISS, Neo4j candidate ranking, or an LLM for comparison output.

**Tech Stack:** Python 3.11, Pydantic, FastAPI, pytest, Ruff

## Global Constraints

- Compare exactly two router-recognized recipes.
- Return common and different ingredients, categories, methods, tools, difficulty, and explicit duration.
- Render missing values as `无法确认`; never infer equality or difference from missing data.
- Keep `/api/v1/search` backward compatible by adding an optional `comparison` field.
- Do not add dependencies or invoke an LLM.

---

## File Map

- Modify `cookqa/models.py`: structured comparison response models and optional `SearchResponse.comparison`.
- Create `cookqa/comparison.py`: deterministic set/scalar comparison logic.
- Modify `cookqa/query/router.py`: require exactly two recognized recipes for comparison.
- Modify `cookqa/service.py`: direct comparison flow returning exactly two results.
- Create `tests/test_comparison.py`: comparator semantics and unknown-field tests.
- Modify `tests/test_router.py`: more-than-two comparison clarification.
- Modify `tests/test_service.py`: coordinator bypass and exact two-recipe result.
- Modify `tests/test_api.py`: JSON response contract.

### Task 1: Comparison Models and Pure Comparator

**Files:**
- Modify: `cookqa/models.py`
- Create: `cookqa/comparison.py`
- Create: `tests/test_comparison.py`

**Interfaces:**
- Produces: `SetComparison(left, right, common, only_left, only_right)`.
- Produces: `ScalarComparison(left, right, relationship)`.
- Produces: `RecipeComparison(left_recipe_id, right_recipe_id, ingredients, categories, methods, tools, difficulty, duration_minutes)`.
- Produces: `RecipeComparator.compare(left: Recipe, right: Recipe) -> RecipeComparison`.

- [ ] **Step 1: Write failing comparator tests**

Create two Recipe fixtures and assert deterministic differences:

```python
comparison = RecipeComparator.compare(kung_pao, laziji)
assert comparison.ingredients.common == ["鸡肉"]
assert comparison.ingredients.only_left == ["花生"]
assert comparison.ingredients.only_right == ["干辣椒"]
assert comparison.difficulty.relationship == "different"
assert comparison.duration_minutes.left == 20
assert comparison.duration_minutes.right == "无法确认"
assert comparison.duration_minutes.relationship == "unknown"
```

Add tests that empty categories/methods/tools become `"无法确认"` and do not produce a false `same` or `different` relationship.

- [ ] **Step 2: Run comparator tests and confirm RED**

Run `python -m pytest tests/test_comparison.py -q`.

Expected: FAIL because the models and comparator do not exist.

- [ ] **Step 3: Add explicit comparison models**

```python
UnknownValue = Literal["无法确认"]


class SetComparison(BaseModel):
    left: list[str] | UnknownValue
    right: list[str] | UnknownValue
    common: list[str] | UnknownValue
    only_left: list[str] | UnknownValue
    only_right: list[str] | UnknownValue


class ScalarComparison(BaseModel):
    left: str | int
    right: str | int
    relationship: Literal["same", "different", "unknown"]


class RecipeComparison(BaseModel):
    left_recipe_id: str
    right_recipe_id: str
    ingredients: SetComparison
    categories: SetComparison
    methods: SetComparison
    tools: SetComparison
    difficulty: ScalarComparison
    duration_minutes: ScalarComparison
```

Add `comparison: RecipeComparison | None = None` to `SearchResponse`.

- [ ] **Step 4: Implement conservative comparison**

Normalize each set with `sorted(set(values))`. Ingredients are always known because the Recipe model requires at least one. For categories/methods/tools, an empty list means unknown. For scalars, `None` maps to `"无法确认"`; if either side is unknown, relationship is `"unknown"`.

- [ ] **Step 5: Run focused tests and Ruff**

Run:

```powershell
python -m pytest tests/test_comparison.py -q
python -m ruff check cookqa/models.py cookqa/comparison.py tests/test_comparison.py
```

Expected: PASS and `All checks passed!`.

- [ ] **Step 6: Commit**

```powershell
git add cookqa/models.py cookqa/comparison.py tests/test_comparison.py
git commit -m "feat: compare structured recipe fields"
```

### Task 2: Dedicated Comparison Routing and Service Flow

**Files:**
- Modify: `cookqa/query/router.py`
- Modify: `cookqa/service.py`
- Modify: `tests/test_router.py`
- Modify: `tests/test_service.py`

**Interfaces:**
- Consumes: `RecipeComparator.compare` and `SearchResponse.comparison` from Task 1.
- Produces: comparison responses with exactly two `SearchResult` records and strategy `['comparison']`.

- [ ] **Step 1: Write failing router and service tests**

Add a coordinator that raises if called:

```python
class ForbiddenCoordinator:
    async def search(self, plan, limit=5):
        raise AssertionError("comparison must not call ranked retrieval")


response = asyncio.run(service.search("宫保鸡丁和辣子鸡有什么区别"))
assert [item.recipe.name for item in response.results] == ["宫保鸡丁", "辣子鸡"]
assert response.retrieval_strategy == ["comparison"]
assert response.comparison is not None
```

Add a router test asserting a query with three recognized dishes and a comparison term returns `clarification_required` with `一次只能比较两道菜`.

- [ ] **Step 2: Run tests and confirm RED**

Run `python -m pytest tests/test_router.py tests/test_service.py -q`.

Expected: FAIL because comparison still enters the coordinator's Neo4j Top 5 flow.

- [ ] **Step 3: Require exactly two comparison targets**

In `QueryRouter.route`, return `recipe_comparison` only when `len(recipes) == 2`. If there are more than two recipes with a comparison term, return `clarification_required` with no retrieval strategy and the clarification text `一次只能比较两道菜，请保留两个菜名。`.

- [ ] **Step 4: Implement direct service comparison**

Build a canonical-name lookup once in `SearchService.__init__`. For a comparison plan, resolve the two recognized names, raise `RetrievalUnavailable("无法定位要比较的两道菜")` unless both exist, and return:

```python
return SearchResponse(
    query_plan=plan,
    results=[
        SearchResult(
            recipe=left,
            score=1.0,
            reasons=["菜谱比较目标"],
            retrieval_sources=["comparison"],
        ),
        SearchResult(
            recipe=right,
            score=1.0,
            reasons=["菜谱比较目标"],
            retrieval_sources=["comparison"],
        ),
    ],
    retrieval_strategy=["comparison"],
    comparison=RecipeComparator.compare(left, right),
)
```

- [ ] **Step 5: Run focused tests and Ruff**

Run:

```powershell
python -m pytest tests/test_router.py tests/test_service.py -q
python -m ruff check cookqa/query/router.py cookqa/service.py tests/test_router.py tests/test_service.py
```

Expected: PASS and `All checks passed!`.

- [ ] **Step 6: Commit**

```powershell
git add cookqa/query/router.py cookqa/service.py tests/test_router.py tests/test_service.py
git commit -m "feat: route recipe comparisons directly"
```

### Task 3: API Contract and P0 Regression Verification

**Files:**
- Modify: `tests/test_api.py`
- Modify: `docs/UNFINISHED.md`

**Interfaces:**
- Verifies: `/api/v1/search` serializes the optional comparison contract.

- [ ] **Step 1: Add a failing API integration test**

Use a comparison-capable fake service and assert:

```python
response = test_client.post(
    "/api/v1/search",
    json={"query": "宫保鸡丁和辣子鸡有什么区别"},
)
payload = response.json()
assert response.status_code == 200
assert len(payload["results"]) == 2
assert payload["comparison"]["ingredients"]["common"] == ["鸡肉"]
assert payload["comparison"]["duration_minutes"]["right"] == "无法确认"
```

- [ ] **Step 2: Run the API test and confirm RED**

Run `python -m pytest tests/test_api.py -q`.

Expected: FAIL until the fake service and response fixture expose the comparison contract.

- [ ] **Step 3: Complete the API fixture and P0 checklist**

Keep the existing endpoint unchanged; update only test fixtures needed to return `SearchResponse.comparison`. After all P0 tests pass, mark Neo4j safe switching and six-query service/API behavior complete in `docs/UNFINISHED.md`, and record the new full test count and verification commands. Do not mark P1 integration, evaluation, or performance items complete.

- [ ] **Step 4: Run complete verification**

Run:

```powershell
$env:TEMP="$PWD\.tmp\pytest-temp"
$env:TMP=$env:TEMP
python -m pytest -q --basetemp .tmp/pytest-p0-final -o cache_dir=.tmp/pytest-cache-p0-final
python -m ruff check .
rg -n "(?i)(api[_-]?key|access[_-]?token|bearer\s+[A-Za-z0-9._-]+|neo4j_password\s*=\s*['\"][^'\"]+)" . --glob '!Data/**' --glob '!.git/**'
git diff --check
```

Expected: all tests pass; Ruff prints `All checks passed!`; secret scan has no real credential matches; `git diff --check` has no output.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_api.py docs/UNFINISHED.md
git commit -m "docs: record P0 completion"
```

