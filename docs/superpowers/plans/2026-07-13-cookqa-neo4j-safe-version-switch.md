# CookQA Neo4j Safe Version Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Neo4j builds version-isolated, activate them through one atomic local pointer, retain the previous version, and support validated rollback.

**Architecture:** Every build gets a unique `data_version`; Neo4j Recipe nodes are keyed by `(recipe_id, data_version)`. `BuildPipeline` writes and validates an invisible candidate, publishes immutable local artifacts, and atomically updates `Data/runtime/active.json` last. Runtime retrieval is always scoped to the manifest version.

**Tech Stack:** Python 3.11, asyncio, pathlib, Pydantic, Neo4j 5.x driver, pytest, FAISS, Ruff

## Global Constraints

- Target Windows single-machine, single-instance deployment.
- `Data/runtime/active.json` is the only active-version pointer.
- Keep the current and previous versions; never delete the active version before activation succeeds.
- Do not add dependencies or expose credentials in errors or logs.
- Use TDD and commit each independently testable task.

---

## File Map

- Create `cookqa/indexing/activation.py`: parse, atomically write, and swap the local active-version pointer.
- Modify `cookqa/indexing/neo4j_writer.py`: versioned graph write, validation, targeted deletion, and cleanup.
- Modify `cookqa/indexing/builder.py`: candidate orchestration, failure cleanup, activation, and rollback validation.
- Modify `cookqa/retrieval/neo4j_store.py`: require `data_version` in every query.
- Modify `cookqa/runtime.py`: pass the manifest version into the graph retriever.
- Modify `cookqa/cli.py`: add explicit `rollback-indexes` operation.
- Create `tests/test_neo4j_writer.py`: graph writer query and failure-safety tests.
- Create `tests/test_activation.py`: pointer atomicity and swap tests.
- Modify `tests/test_builder.py`: activation ordering, cleanup, failure injection, and rollback tests.
- Modify `tests/test_neo4j_queries.py`: retrieval version-scoping tests.
- Modify `tests/test_runtime.py`: runtime passes the active version to Neo4j.
- Create `tests/test_cli.py`: rollback command parsing and dispatch tests.

### Task 1: Version-Isolated Neo4j Writer

**Files:**
- Create: `tests/test_neo4j_writer.py`
- Modify: `cookqa/indexing/neo4j_writer.py`

**Interfaces:**
- Produces: `Neo4jGraphWriter.write_version(recipes, data_version) -> None`
- Produces: `Neo4jGraphWriter.validate_version(recipes, data_version) -> set[str]`
- Produces: `Neo4jGraphWriter.delete_version(data_version) -> None`
- Produces: `Neo4jGraphWriter.cleanup_versions(keep_versions) -> None`

- [ ] **Step 1: Write failing graph-writer tests**

Create a recording fake driver and assert the write query uses the composite key, never performs an unscoped delete, validation returns exactly the requested version, and cleanup is parameterized:

```python
class RecordingDriver:
    def __init__(self, ids=None):
        self.ids = ids or []
        self.calls = []

    def execute_query(self, cypher, **parameters):
        self.calls.append((cypher, parameters))
        if "RETURN recipe.recipe_id AS recipe_id" in cypher:
            return ([{"recipe_id": item} for item in self.ids], None, None)
        return ([], None, None)


def test_writer_keeps_recipe_versions_isolated(recipe):
    driver = RecordingDriver([recipe.recipe_id])
    writer = Neo4jGraphWriter(driver)

    asyncio.run(writer.write_version([recipe], "v2"))
    ids = asyncio.run(writer.validate_version([recipe], "v2"))

    all_cypher = "\n".join(call[0] for call in driver.calls)
    assert "recipe_id: item.recipe_id, data_version: $data_version" in all_cypher
    assert "MATCH (recipe:Recipe) DETACH DELETE recipe" not in all_cypher
    assert ids == {recipe.recipe_id}
```

Add tests that `delete_version("candidate")` passes only `$data_version`, `cleanup_versions({"v1", "v2"})` passes `$keep_versions`, and an empty keep set raises `ValueError`.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```powershell
python -m pytest tests/test_neo4j_writer.py -q
```

Expected: FAIL because the four versioned writer methods and composite Recipe key do not exist.

- [ ] **Step 3: Implement the minimal versioned writer**

Replace the destructive flow with parameterized queries:

```python
_UPSERT_CYPHER = """
UNWIND $recipes AS item
MERGE (recipe:Recipe {
  recipe_id: item.recipe_id,
  data_version: $data_version
})
SET recipe.name = item.name,
    recipe.aliases = item.aliases,
    recipe.summary = item.summary,
    recipe.difficulty = item.difficulty,
    recipe.calories = item.calories,
    recipe.duration_minutes = item.duration_minutes,
    recipe.steps = item.steps,
    recipe.source_path = item.source_path,
    recipe.source_version = item.source_version
WITH recipe, item
FOREACH (ingredient IN item.ingredients |
  MERGE (node:Ingredient {name: ingredient.name})
  MERGE (recipe)-[relation:REQUIRES]->(node)
  SET relation.amount = ingredient.amount,
      relation.unit = ingredient.unit,
      relation.optional = ingredient.optional,
      relation.raw = ingredient.raw)
FOREACH (name IN item.categories |
  MERGE (node:Category {name: name})
  MERGE (recipe)-[:BELONGS_TO]->(node))
FOREACH (name IN item.methods |
  MERGE (node:Method {name: name})
  MERGE (recipe)-[:USES_METHOD]->(node))
FOREACH (name IN item.tools |
  MERGE (node:Tool {name: name})
  MERGE (recipe)-[:USES_TOOL]->(node))
FOREACH (name IN item.tags |
  MERGE (node:Tag {name: name})
  MERGE (recipe)-[:HAS_TAG]->(node))
"""

_VERSION_IDS_CYPHER = """
MATCH (recipe:Recipe {data_version: $data_version})
RETURN recipe.recipe_id AS recipe_id
"""

_DELETE_VERSION_CYPHER = """
MATCH (recipe:Recipe {data_version: $data_version})
DETACH DELETE recipe
"""

_CLEANUP_VERSIONS_CYPHER = """
MATCH (recipe:Recipe)
WHERE NOT recipe.data_version IN $keep_versions
DETACH DELETE recipe
"""
```

Implement synchronous helpers executed with `asyncio.to_thread`. `validate_version` must compare the returned IDs with `{recipe.recipe_id for recipe in recipes}` and raise `ValueError("Neo4j recipe_id 集合与候选版本不一致")` on mismatch.

- [ ] **Step 4: Run focused tests and Ruff**

Run:

```powershell
python -m pytest tests/test_neo4j_writer.py -q
python -m ruff check cookqa/indexing/neo4j_writer.py tests/test_neo4j_writer.py
```

Expected: all focused tests pass and Ruff prints `All checks passed!`.

- [ ] **Step 5: Commit**

```powershell
git add cookqa/indexing/neo4j_writer.py tests/test_neo4j_writer.py
git commit -m "feat: isolate Neo4j recipe versions"
```

### Task 2: Atomic Active Pointer

**Files:**
- Create: `cookqa/indexing/activation.py`
- Create: `tests/test_activation.py`

**Interfaces:**
- Produces: `ActiveVersion(version: str, previous_version: str | None)`
- Produces: `read_active_version(data_dir: Path) -> ActiveVersion | None`
- Produces: `activate_version(data_dir: Path, version: str, previous_version: str | None) -> ActiveVersion`
- Produces: `swap_to_previous(data_dir: Path) -> ActiveVersion`

- [ ] **Step 1: Write failing pointer tests**

```python
def test_activate_records_previous_version(tmp_path):
    activate_version(tmp_path, "v1", None)
    state = activate_version(tmp_path, "v2", "v1")
    saved = json.loads((tmp_path / "runtime" / "active.json").read_text("utf-8"))
    assert state == ActiveVersion(version="v2", previous_version="v1")
    assert saved == {"version": "v2", "previous_version": "v1"}


def test_swap_to_previous_is_reversible(tmp_path):
    activate_version(tmp_path, "v2", "v1")
    assert swap_to_previous(tmp_path) == ActiveVersion(version="v1", previous_version="v2")
```

Also monkeypatch `os.replace` to raise `OSError` and assert the original `active.json` bytes remain unchanged.

- [ ] **Step 2: Run tests and confirm RED**

Run `python -m pytest tests/test_activation.py -q`.

Expected: FAIL because `cookqa.indexing.activation` does not exist.

- [ ] **Step 3: Implement atomic pointer helpers**

```python
@dataclass(frozen=True, slots=True)
class ActiveVersion:
    version: str
    previous_version: str | None = None


def activate_version(data_dir: Path, version: str, previous_version: str | None) -> ActiveVersion:
    state = ActiveVersion(version=version, previous_version=previous_version)
    runtime_dir = data_dir / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    temporary = runtime_dir / f"active.{uuid.uuid4().hex}.tmp"
    payload = {"version": state.version}
    if state.previous_version is not None:
        payload["previous_version"] = state.previous_version
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.replace(temporary, runtime_dir / "active.json")
    finally:
        temporary.unlink(missing_ok=True)
    return state
```

`swap_to_previous` must reject a missing pointer or missing `previous_version` before writing.

- [ ] **Step 4: Run focused tests and Ruff**

Run:

```powershell
python -m pytest tests/test_activation.py -q
python -m ruff check cookqa/indexing/activation.py tests/test_activation.py
```

Expected: PASS and `All checks passed!`.

- [ ] **Step 5: Commit**

```powershell
git add cookqa/indexing/activation.py tests/test_activation.py
git commit -m "feat: manage atomic index activation"
```

### Task 3: Safe Build Orchestration and Rollback

**Files:**
- Modify: `cookqa/indexing/builder.py`
- Modify: `tests/test_builder.py`

**Interfaces:**
- Consumes: the four `GraphWriter` version methods from Task 1.
- Consumes: activation helpers from Task 2.
- Produces: `BuildPipeline.rollback(data_dir: Path) -> BuildResult`.

- [ ] **Step 1: Replace the fake writer and add failure-injection tests**

Use a fake that records version calls:

```python
class FakeGraphWriter:
    def __init__(self, fail_at=None):
        self.ids = set()
        self.fail_at = fail_at
        self.deleted = []
        self.kept = []

    async def write_version(self, recipes, data_version):
        self.ids = {recipe.recipe_id for recipe in recipes}
        if self.fail_at == "write":
            raise RuntimeError("write failed")

    async def validate_version(self, recipes, data_version):
        if self.fail_at == "validate":
            raise ValueError("validation failed")
        return set(self.ids)

    async def delete_version(self, data_version):
        self.deleted.append(data_version)

    async def cleanup_versions(self, keep_versions):
        self.kept.append(set(keep_versions))
        if self.fail_at == "cleanup":
            raise RuntimeError("cleanup failed")
```

Add tests for write failure, validation failure, `os.replace` activation failure, cleanup failure, successful retention of current/previous, and successful/failed rollback. Every pre-activation failure must assert the old `active.json` is byte-for-byte unchanged.

- [ ] **Step 2: Run builder tests and confirm RED**

Run `python -m pytest tests/test_builder.py -q`.

Expected: FAIL because `BuildPipeline` still calls `replace_recipes` and has no rollback.

- [ ] **Step 3: Implement candidate orchestration**

Update the protocol to the Task 1 methods. Generate a collision-free candidate version:

```python
data_version = f"{source_version[:12]}-{id_hash[:12]}-{uuid.uuid4().hex[:8]}"
```

Track `candidate_written`, `artifact_dir`, and `activated`. The critical sequence is:

```python
previous = read_active_version(data_dir)
await self.graph_writer.write_version(recipes, data_version)
candidate_written = True
graph_ids = await self.graph_writer.validate_version(recipes, data_version)
validate_manifest(
    manifest,
    bm25_ids=set(bm25.recipe_ids),
    faiss_ids=set(vector_index.recipe_ids),
    graph_ids=graph_ids,
    embedding_dimension=vector_index.dimension,
)
os.replace(staging_dir, artifact_dir)
activate_version(data_dir, data_version, previous.version if previous else None)
activated = True
```

Before activation, exceptions delete only the candidate graph version and candidate artifact. After activation, cleanup is best effort:

```python
keep = {data_version}
if previous is not None:
    keep.add(previous.version)
try:
    await self.graph_writer.cleanup_versions(keep)
except Exception as exc:
    logger.warning(
        "Neo4j 历史版本清理失败 version=%s error=%s",
        data_version,
        exc.__class__.__name__,
    )
```

Do not log exception messages or connection configuration.

- [ ] **Step 4: Implement validated rollback**

`rollback` must read `previous_version`, load the previous artifact's manifest/BM25/FAISS/recipes, call `validate_version`, run `validate_manifest`, then call `swap_to_previous`. Validation failure or `os.replace` failure must leave the original pointer unchanged.

- [ ] **Step 5: Run builder and activation tests**

Run:

```powershell
python -m pytest tests/test_builder.py tests/test_activation.py tests/test_neo4j_writer.py -q
python -m ruff check cookqa/indexing tests/test_builder.py tests/test_activation.py tests/test_neo4j_writer.py
```

Expected: PASS and `All checks passed!`.

- [ ] **Step 6: Commit**

```powershell
git add cookqa/indexing/builder.py tests/test_builder.py
git commit -m "feat: activate and roll back index versions safely"
```

### Task 4: Runtime Version Scoping and Rollback CLI

**Files:**
- Modify: `cookqa/retrieval/neo4j_store.py`
- Modify: `cookqa/runtime.py`
- Modify: `cookqa/cli.py`
- Modify: `tests/test_neo4j_queries.py`
- Modify: `tests/test_runtime.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Produces: `build_candidate_query(plan, limit, data_version)`.
- Produces: `Neo4jRetriever(driver, data_version, database=None)`.
- Produces CLI: `python -m cookqa.cli rollback-indexes --data-dir Data`.

- [ ] **Step 1: Write failing retrieval and runtime tests**

```python
cypher, parameters = build_candidate_query(plan, limit=5, data_version="v2")
assert "recipe.data_version = $data_version" in cypher
assert parameters["data_version"] == "v2"
```

Monkeypatch `runtime.Neo4jRetriever` with a recorder and assert `build_runtime` passes `manifest.data_version`. Add parser/dispatch tests for `rollback-indexes` without connecting to a real database.

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```powershell
python -m pytest tests/test_neo4j_queries.py tests/test_runtime.py tests/test_cli.py -q
```

Expected: FAIL because query and retriever constructors lack `data_version`, and the CLI lacks rollback.

- [ ] **Step 3: Scope every graph query to the manifest version**

Change the query predicate to start with:

```cypher
MATCH (recipe:Recipe)
WHERE recipe.data_version = $data_version
  AND ($required_ingredients = [] OR ALL(name IN $required_ingredients WHERE
    EXISTS { MATCH (recipe)-[:REQUIRES]->(required:Ingredient) WHERE required.name = name }))
  AND ($excluded_ingredients = [] OR NONE(name IN $excluded_ingredients WHERE
    EXISTS { MATCH (recipe)-[:REQUIRES]->(excluded:Ingredient) WHERE excluded.name = name }))
  AND ($max_minutes IS NULL OR (recipe.duration_minutes IS NOT NULL
    AND recipe.duration_minutes <= $max_minutes))
  AND ($categories = [] OR EXISTS {
    MATCH (recipe)-[:BELONGS_TO]->(category:Category) WHERE category.name IN $categories
  })
  AND ($tools = [] OR ALL(name IN $tools WHERE
    EXISTS { MATCH (recipe)-[:USES_TOOL]->(tool:Tool) WHERE tool.name = name }))
```

Store `data_version` in `Neo4jRetriever` and pass it to `build_candidate_query`. Construct it in runtime as `Neo4jRetriever(driver, manifest.data_version)`.

- [ ] **Step 4: Add rollback CLI dispatch**

Add `rollback-indexes` with `--data-dir`. Reuse the same Neo4j credential checks and driver setup as build, then call:

```python
result = await BuildPipeline(
    OllamaClient(settings),
    Neo4jGraphWriter(driver),
).rollback(args.data_dir)
```

Print only status, version, recipe count, and artifact path.

- [ ] **Step 5: Run focused and regression tests**

Run:

```powershell
python -m pytest tests/test_neo4j_queries.py tests/test_runtime.py tests/test_cli.py -q
python -m pytest -q --basetemp .tmp/pytest-p0-neo4j -o cache_dir=.tmp/pytest-cache-p0-neo4j
python -m ruff check .
```

Expected: all tests pass and Ruff prints `All checks passed!`.

- [ ] **Step 6: Commit**

```powershell
git add cookqa/retrieval/neo4j_store.py cookqa/runtime.py cookqa/cli.py tests/test_neo4j_queries.py tests/test_runtime.py tests/test_cli.py
git commit -m "feat: scope and roll back active graph versions"
```

