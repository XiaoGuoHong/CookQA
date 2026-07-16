# CookQA Phase 3 Pantry Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Add a structured pantry-to-recipe workflow while preserving existing free-text search, recipe detail, and independent streaming Q&A behavior.

**Architecture:** Add a framework-independent pantry matching domain service that normalizes user ingredients, applies hard constraints, computes ingredient coverage, and returns stable ready/near/related groups. Inject it into the existing runtime and expose it through validated FastAPI models; extend the static UI to collect and render the structured response.

**Tech Stack:** Python 3.11+, Pydantic, FastAPI, pytest, static HTML/CSS/JavaScript.

## Global Constraints

- Do not change the 200-recipe dataset, index format, BM25/FAISS/Neo4j/RRF weights, or evaluation data.
- Pantry matching must not call LLM, Neo4j, FAISS, or Ollama.
- Existing `/api/v1/search`, recipe detail, comparison, and streaming answer endpoints remain compatible.
- Do not persist unsubmitted input or personal state.
- Default tests must not connect to real Neo4j or Ollama.

### Task 1: Pantry domain models and matcher

**Files:**
- Create: `cookqa/pantry.py`
- Create: `config/pantry_staples.json`
- Create: `tests/test_pantry.py`

- [ ] Write failing tests for alias normalization, duplicate/blank handling, staple toggling, optional ingredients, exclusion/time/spicy hard filters, group boundaries, five-item limits, coverage, and stable sorting.
- [ ] Run `pytest tests/test_pantry.py -q` and confirm the new behavior fails because the pantry module/configuration is absent.
- [ ] Implement `PantryMatcher` with typed result objects, normalization through `normalize_ingredient`, explicit warnings for unrecognized inputs, visible staples that only affect missing-item calculation, and deterministic per-group ordering.
- [ ] Run `pytest tests/test_pantry.py -q` and confirm it passes.

### Task 2: API models, service injection, and endpoint

**Files:**
- Modify: `cookqa/models.py`
- Modify: `cookqa/runtime.py`
- Modify: `api/app.py`
- Modify: `tests/test_api.py`

- [ ] Add failing tests for valid pantry responses, 422 invalid input, conflicting existing/excluded ingredients, and service-level compatibility.
- [ ] Run the focused API tests and confirm failure before implementation.
- [ ] Add `PantrySearchRequest`, `PantryMatch`, and `PantrySearchResponse`; inject the matcher into runtime/app creation and expose `POST /api/v1/pantry/search` with 503 readiness behavior matching existing search.
- [ ] Run the focused API tests and then the existing API suite.

### Task 3: Pantry UI and detail ingredient states

**Files:**
- Modify: `web/index.html`
- Modify: `web/styles.css`
- Modify: `web/app.js`
- Modify: `tests/test_web.py`

- [ ] Add failing static-asset tests for the two entry modes, pantry endpoint, grouped result labels, ingredient-state rendering, and Q&A controls.
- [ ] Run the focused web tests and confirm failure before implementation.
- [ ] Add keyboard-accessible mode switching, tag inputs, hard filters, staple toggle, pantry request/rendering, detail ingredient states, and stop/retry/copy controls without changing the existing search flow.
- [ ] Run the web tests and manually syntax-check the JavaScript.

### Task 4: Documentation and quality verification

**Files:**
- Modify: `README.md`
- Modify: `docs/UNFINISHED.md`

- [ ] Update project status and usage documentation to reflect implemented Phase3 behavior without claiming external-environment acceptance.
- [ ] Run `pytest`, `ruff check .`, `pip check`, and `git diff --check`; inspect the diff for scope and accidental runtime/data artifacts.
