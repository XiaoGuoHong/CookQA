# CookQA P2B Data and Operations Implementation Plan

> **Execution rule:** implement each task test-first, observe the focused test fail for the expected reason, then make the smallest production change and rerun the full quality gate.

**Goal:** Close CookQA Phase 2 by making Neo4j schema initialization idempotent, filtering nullable relationship properties, adding auditable and dry-run-first version cleanup, removing the ambiguous empty selection file, and proving rebuild/activation/rollback on the real 200-recipe dataset.

**Architecture:** Keep `Data/runtime/active.json` as the only visibility switch. `Neo4jGraphWriter` owns schema and graph-version primitives; `BuildPipeline` owns protected-version planning and coordinates graph/local deletion. Structured JSONL operations are written under ignored `Data/runtime/`, and the CLI exposes the same cleanup planner in dry-run mode by default.

**Tech stack:** Python 3.11, asyncio, Neo4j 5.x driver, pytest, Ruff, existing FastAPI/Ollama/FAISS stack. No new dependency.

---

## Task 1: Idempotent Neo4j schema and clean relationship properties

**Files:**

- Modify: `cookqa/indexing/neo4j_writer.py`
- Modify: `cookqa/indexing/builder.py`
- Modify: `tests/test_neo4j_writer.py`
- Modify: `tests/test_builder_versions.py`
- Modify: `tests/test_builder.py`

**Steps:**

1. Add failing writer tests that require named `IF NOT EXISTS` constraints for `(Recipe.recipe_id, Recipe.data_version)` and taxonomy-node names, plus a `Recipe.data_version` index.
2. Add a failing test that calls schema setup twice and verifies both runs use idempotent statements and validate the expected names via `SHOW CONSTRAINTS` / `SHOW INDEXES`.
3. Add a failing payload test proving `amount=None` and `unit=None` are absent from relationship properties while `raw` and `optional=False` remain.
4. Add `ensure_schema()` to `Neo4jGraphWriter`; run it before candidate graph writes. A schema failure must occur before activation and preserve the existing `active.json`.
5. Replace direct nullable relationship assignments with a prepared property map and `SET relation = ingredient.relationship_properties`.
6. Run:

```powershell
python -m pytest -q tests/test_neo4j_writer.py tests/test_builder.py tests/test_builder_versions.py -p no:cacheprovider
python -m ruff check cookqa/indexing tests/test_neo4j_writer.py tests/test_builder.py tests/test_builder_versions.py
git diff --check
```

7. Commit: `feat: enforce CookQA Neo4j schema`.

## Task 2: Protected cleanup planning and structured operations audit

**Files:**

- Create: `cookqa/indexing/operations.py`
- Modify: `cookqa/indexing/neo4j_writer.py`
- Modify: `cookqa/indexing/builder.py`
- Create: `tests/test_index_operations.py`
- Modify: `tests/test_builder_versions.py`

**Steps:**

1. Add failing tests for a cleanup plan that always protects the active version, previous version, and explicit `--keep` versions.
2. Require candidates to be valid `Data/indexes/<version>/index-manifest.json` directories whose manifest version matches the directory name; report invalid entries and graph-only versions without deleting them.
3. Add failing tests proving dry-run does not delete graph or local versions and actual cleanup deletes only eligible candidates from Neo4j first, then local disk.
4. Add failing tests for JSONL audit entries covering activation, rollback, cleanup dry-run, cleanup success, and safe failure categories without exception text or credentials.
5. Implement immutable cleanup-plan/result dataclasses, UTC timestamped JSONL append, and graph version listing.
6. Route post-activation automatic cleanup through the same planner. Cleanup failure remains non-fatal after activation but is recorded as failed; activation and rollback validation semantics remain unchanged.
7. Run:

```powershell
python -m pytest -q tests/test_index_operations.py tests/test_builder_versions.py tests/test_neo4j_writer.py -p no:cacheprovider
python -m ruff check cookqa/indexing tests/test_index_operations.py tests/test_builder_versions.py tests/test_neo4j_writer.py
git diff --check
```

8. Commit: `feat: audit index version operations`.

## Task 3: Dry-run CLI, single selection source, and recovery handbook

**Files:**

- Modify: `cookqa/cli.py`
- Modify: `tests/test_cli.py`
- Delete: `config/recipe-selection.txt`
- Create: `docs/INDEX_RECOVERY.md`
- Modify: `README.md`
- Modify: `docs/UNFINISHED.md`

**Steps:**

1. Add failing parser/dispatch tests for `cleanup-indexes --data-dir Data`, repeatable `--keep VERSION`, and explicit `--apply`; dry-run is the default.
2. Implement CLI wiring through the same `BuildPipeline.cleanup_history()` path and emit only structured JSON results.
3. Delete `config/recipe-selection.txt` after the repository-wide reference check confirms no runtime/test/config consumer. Keep `config/recipe-selection-mvp.txt` as the sole 200-recipe build input.
4. Write `docs/INDEX_RECOVERY.md` with prerequisites, build, readiness validation, cleanup dry-run, explicit apply, rollback, post-rollback verification, failure behavior, audit-log location, and credential-safe examples.
5. Update README and unfinished-status documentation without claiming P2 complete before real acceptance.
6. Run:

```powershell
python -m pytest -q tests/test_cli.py tests/test_index_operations.py -p no:cacheprovider
python -m ruff check cookqa/cli.py tests/test_cli.py
rg -n "recipe-selection\\.txt" cookqa api scripts tests config README.md
git diff --check
```

7. Commit: `feat: add safe index cleanup workflow`.

## Task 4: Full regression and real 200-recipe operations acceptance

**Files:**

- Modify only if evidence requires a scoped fix: P2B files above
- Modify: `README.md`
- Modify: `docs/UNFINISHED.md`
- Runtime artifacts only, ignored by Git: `Data/runtime/*.json`, `Data/runtime/*.jsonl`

**Steps:**

1. Run the default quality gate with repository-local temp directories:

```powershell
$env:TEMP="$PWD\.tmp\pytest-temp"
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
python -m pytest -q -p no:cacheprovider
python -m ruff check .
python -m pip check
git diff --check
```

2. With real Neo4j/Ollama running and `COOKQA_DATA_DIR` pointing at the existing local data, run the explicit integration suite.
3. Build a fresh 200-recipe candidate and confirm schema names, manifest count/hash, activation to the new version, and retention of the previous version.
4. Run cleanup dry-run and prove the new active and previous versions are protected; do not apply destructive cleanup during acceptance unless an eligible, verified historical version exists and the plan is reviewed.
5. Execute validated rollback once, confirm the former active version becomes `previous_version`, then validate `/ready` and integration tests.
6. Rebuild/activate the intended final version if rollback changed the desired final pointer.
7. Run the fixed 50-query benchmark, cold-start report, and HTTP/Web UI smoke checks. Required thresholds remain Recall@5 >= 0.90, hard-filter violations = 0, search P95 <= 1000ms, first-token P95 <= 3000ms, and zero required failures.
8. Verify `SHOW CONSTRAINTS`, `SHOW INDEXES`, operation-audit entries, Git ignored runtime artifacts, and absence of sensitive output.
9. Update README and `docs/UNFINISHED.md` with fresh evidence, then rerun the complete quality gate.
10. Request code review, resolve only verified P2B findings, and commit: `docs: complete CookQA Phase 2 acceptance`.

