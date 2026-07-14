# CookQA P1 Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the P1 runtime semantics and real 200-recipe P50/P95 acceptance gates, then publish truthful README status.

**Architecture:** Keep the existing FastAPI, QueryRouter, BM25/FAISS/Neo4j retrieval and Ollama boundaries. Add one shared runtime alias loader, represent spicy intent as explicit query constraints, and make the benchmark consume the existing API without bypassing production retrieval.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, Neo4j, FAISS, Ollama, pytest, httpx.

## Global Constraints

- Use the fixed HowToCook commit `cbc524e28a88bf5ccc6e094004cfbeba1ea6fdf9`.
- Validate against exactly 200 selected recipes and the real local Neo4j/Ollama services.
- Do not print or persist Neo4j credentials, tokens, cookies, or authorization headers.
- Use TDD: each production behavior change gets a failing test before implementation.
- Do not claim P1 completion until the real benchmark targets pass.

### Task 1: Runtime alias loading

**Files:**
- Modify: `cookqa/runtime.py`
- Test: `tests/test_runtime.py`

- [ ] Add a failing test proving `build_runtime()` passes the configured alias map to `QueryRouter`.
- [ ] Run the focused test and confirm it fails because runtime currently passes no aliases.
- [ ] Add a small JSON loader for `config/ingredient_aliases.json`, resolve it from the repository root, and pass the mapping as `ingredient_aliases=`.
- [ ] Run the focused test and the existing runtime/router tests.

### Task 2: Spicy semantic hard filters

**Files:**
- Modify: `cookqa/models.py`, `cookqa/query/router.py`, `cookqa/retrieval/fusion.py`
- Test: `tests/test_router.py`, `tests/test_fusion.py`

- [ ] Add failing tests for `不辣` producing a structured spicy exclusion and `辣` producing a structured spicy requirement without adding `辣` as an ingredient.
- [ ] Add failing filter tests for recipes with chili/辣椒 evidence, recipes without it, and unknown spicy status.
- [ ] Implement the smallest structured constraint representation and shared spicy ingredient evidence helper.
- [ ] Ensure “不含辣椒” remains an explicit ingredient exclusion and is not rewritten as subjective spicy language.
- [ ] Run focused router/fusion tests and the full unit suite.

### Task 3: Real P50/P95 benchmark

**Files:**
- Modify: `scripts/benchmark.py`
- Test: `tests/test_benchmark.py`

- [ ] Add failing tests for percentile output, repeated warm samples, and report target fields.
- [ ] Implement P50/P95 for search and first-token latency, preserve Recall@5 and hard-filter checks, and include sample/failure counts.
- [ ] Add optional repeat controls while keeping the current CLI defaults deterministic and local.
- [ ] Run benchmark unit tests and lint.

### Task 4: Real acceptance and optimization

**Files:**
- Modify only the directly failing retrieval/router/service files revealed by the benchmark.
- Create: `Data/runtime/benchmark-report.json` as ignored runtime output.

- [ ] Start/verify Neo4j and Ollama with the two configured models.
- [ ] Build the 200-recipe BM25/FAISS/Neo4j version and verify `/ready`.
- [ ] Run the fixed 50-case benchmark with warmups and repeated samples.
- [ ] If targets fail, add a regression test for the measured failure, implement one minimal optimization, and rerun the focused test plus benchmark.
- [ ] Stop only when Recall@5 >= 0.90, hard-filter violations = 0, search P95 <= 1000ms, and first-token P95 <= 3000ms.

### Task 5: Documentation closure

**Files:**
- Modify: `README.md`, `docs/UNFINISHED.md`

- [ ] Update setup, runtime model tags, benchmark command, measured report path, and P1 status.
- [ ] Record exact real acceptance evidence without embedding credentials or unstable claims.
- [ ] Run final tests, lint, HTTP smoke checks, `git diff --check`, and `git status --short`.
