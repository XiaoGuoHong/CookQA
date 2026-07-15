# CookQA P2A Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver P2A's repeatable verification layer: warning-free in-process API tests, opt-in real-service integration tests, diagnostic benchmark reports, and independent cold-start measurement.

**Architecture:** Keep production retrieval and API behavior unchanged. Replace deprecated synchronous TestClient usage with one async ASGI test helper, isolate real-service tests behind a pytest marker, extend the existing HTTP benchmark with pure diagnostic aggregation, and add a separate process-level cold-start script whose orchestration is dependency-injected for unit tests.

**Tech Stack:** Python 3.11, FastAPI, httpx, pytest, pytest-asyncio, subprocess, PowerShell, Neo4j, Ollama.

## Global Constraints

- Keep the fixed HowToCook source commit `cbc524e28a88bf5ccc6e094004cfbeba1ea6fdf9` and exactly 200 selected recipes.
- Do not change retrieval semantics, ranking weights, model tags, index formats, or Web UI behavior in P2A.
- Default pytest must not connect to Neo4j or Ollama; real-service tests run only with `-m integration`.
- Keep existing benchmark Recall@5, hard-filter, warmed search, and first-token fields compatible.
- Cold-start means a new CookQA API process through first `/ready` and first fixed search; do not restart Neo4j or unload Ollama models.
- Do not print or persist passwords, tokens, cookies, authorization headers, or sensitive environment variables.
- Do not modify or commit the existing untracked `tests/.sandbox-probe`.
- Every production behavior change follows RED, GREEN, REFACTOR; commit only focused files after verification.

---

## File Structure

- Create `tests/http_client.py`: one async context manager for in-process ASGI requests.
- Modify `tests/test_api.py`, `tests/test_api_query_types.py`, `tests/test_web.py`: consume the async helper without changing assertions.
- Create `tests/test_test_configuration.py`: lock the integration marker and default deselection contract.
- Create `tests/test_integration_services.py`: opt-in HTTP checks against a running real CookQA service.
- Modify `pytest.ini`: register `integration` and exclude it by default; remove the obsolete warning filter.
- Modify `scripts/benchmark.py`: collect per-case diagnostics and aggregate misses, intents, degradation, and safe failures.
- Modify `tests/test_benchmark.py`: unit-test diagnostic aggregation and report integration.
- Create `scripts/cold_start.py`: process-level repeated cold-start runner and JSON report writer.
- Create `tests/test_cold_start.py`: cover success, ready timeout, early process exit, and first-search failure.
- Modify `README.md`, `docs/UNFINISHED.md`: document P2A commands and record only freshly verified results.

### Task 1: Warning-free ASGI API test client

**Files:**
- Create: `tests/http_client.py`
- Modify: `tests/test_api.py`
- Modify: `tests/test_api_query_types.py`
- Modify: `tests/test_web.py`
- Modify: `pytest.ini`

**Interfaces:**
- Produces: `asgi_client(app: Any) -> AsyncIterator[httpx.AsyncClient]` as an async context manager.
- Consumes: FastAPI applications returned by `api.app.create_app()`.

- [ ] **Step 1: Prove the current warning is real**

Run:

```powershell
$env:TEMP="$PWD\.tmp\pytest-temp"
$env:TMP=$env:TEMP
python -m pytest tests/test_api.py tests/test_api_query_types.py tests/test_web.py -q `
  -p no:cacheprovider -W error::DeprecationWarning
```

Expected: FAIL from Starlette TestClient/httpx compatibility, proving the warning filter currently masks a real warning.

- [ ] **Step 2: Add the async ASGI helper**

Create `tests/http_client.py`:

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx


@asynccontextmanager
async def asgi_client(app: Any) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client
```

- [ ] **Step 3: Convert API tests without changing behavior**

Replace `TestClient` factories with app factories, mark request tests `async def`, and use:

```python
async with asgi_client(app(ready=False)) as client:
    response = await client.get("/ready")
```

For parameterized query-type tests, build the app once per test and call `await client.post(...)`. For Web tests, use the same helper with `mount_web=True`. Keep every existing response assertion unchanged.

- [ ] **Step 4: Remove the obsolete warning filter and verify GREEN**

Delete the `filterwarnings` block from `pytest.ini`, then run:

```powershell
python -m pytest tests/test_api.py tests/test_api_query_types.py tests/test_web.py -q `
  -p no:cacheprovider -W error::DeprecationWarning
```

Expected: all focused tests PASS with no deprecation warnings.

- [ ] **Step 5: Run the full default suite and commit**

```powershell
python -m pytest -q -p no:cacheprovider
python -m ruff check tests/http_client.py tests/test_api.py tests/test_api_query_types.py tests/test_web.py
git add pytest.ini tests/http_client.py tests/test_api.py tests/test_api_query_types.py tests/test_web.py
git commit -m "test: remove deprecated API test client"
```

Expected: all default tests PASS; Ruff reports `All checks passed!`.

### Task 2: Explicit real-service integration lane

**Files:**
- Create: `tests/test_test_configuration.py`
- Create: `tests/test_integration_services.py`
- Modify: `pytest.ini`

**Interfaces:**
- Consumes: `COOKQA_INTEGRATION_BASE_URL`, defaulting to `http://127.0.0.1:8000` only when integration tests are explicitly selected.
- Produces: pytest marker `integration` and two real HTTP assertions: readiness consistency and non-degraded search.

- [ ] **Step 1: Write the failing configuration contract**

Create `tests/test_test_configuration.py`:

```python
from pathlib import Path


def test_integration_tests_are_registered_and_excluded_by_default():
    config = Path("pytest.ini").read_text(encoding="utf-8")

    assert 'addopts = -m "not integration"' in config
    assert "integration: requires a running CookQA service" in config
```

Run:

```powershell
python -m pytest tests/test_test_configuration.py -q -p no:cacheprovider
```

Expected: FAIL because `pytest.ini` does not yet define the marker or default exclusion.

- [ ] **Step 2: Register and default-exclude integration tests**

Set `pytest.ini` to include:

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
addopts = -m "not integration"
markers =
    integration: requires a running CookQA service with real Neo4j, Ollama, and active indexes
```

Run the focused configuration test. Expected: PASS.

- [ ] **Step 3: Add the real-service tests**

Create `tests/test_integration_services.py`:

```python
from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.integration


def base_url() -> str:
    return os.getenv("COOKQA_INTEGRATION_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


@pytest.mark.asyncio
async def test_real_service_is_ready_with_200_recipe_manifest():
    async with httpx.AsyncClient(base_url=base_url(), timeout=30) as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["manifest"]["recipe_count"] == 200
    assert all(item["available"] for item in payload["components"].values())


@pytest.mark.asyncio
async def test_real_search_uses_no_degraded_components():
    async with httpx.AsyncClient(base_url=base_url(), timeout=30) as client:
        response = await client.post("/api/v1/search", json={"query": "可乐鸡翅怎么做"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    assert payload["degradation"]["degraded"] is False
    assert payload["degradation"]["unavailable_components"] == []
```

- [ ] **Step 4: Verify isolation and explicit selection**

Run:

```powershell
python -m pytest tests/test_integration_services.py -q -p no:cacheprovider
python -m pytest tests/test_test_configuration.py -q -p no:cacheprovider
```

Expected: first command reports two deselected tests; second command PASS.

With a real service running, run:

```powershell
python -m pytest -q -m integration -p no:cacheprovider
```

Expected: two integration tests PASS. If the service is not ready, the tests fail rather than silently skip.

- [ ] **Step 5: Commit**

```powershell
git add pytest.ini tests/test_test_configuration.py tests/test_integration_services.py
git commit -m "test: add opt-in real service checks"
```

### Task 3: Diagnostic benchmark report

**Files:**
- Modify: `scripts/benchmark.py`
- Modify: `tests/test_benchmark.py`

**Interfaces:**
- Produces: `summarize_case_diagnostics(records: list[dict]) -> dict`.
- Produces report keys: `misses`, `intent_summary`, `degradation_summary`, `failure_summary`.
- Keeps existing keys: `case_count`, `evaluated_count`, `recall_at_5`, latency summaries, target booleans, and `failures`.

- [ ] **Step 1: Write failing pure aggregation tests**

Add records representing one hit, one miss with a wrong actual intent, two degraded components, and one HTTP failure. Assert:

```python
diagnostics = summarize_case_diagnostics(records)

assert diagnostics["misses"] == [
    {
        "case_id": "case-002",
        "query": "推荐不辣的虾菜",
        "expected_recipe_ids": ["expected-2"],
        "returned_recipe_ids": ["actual-2"],
        "expected_intent": "conditional_recommendation",
        "actual_intent": "semantic_recommendation",
    }
]
assert diagnostics["intent_summary"]["conditional_recommendation"] == {
    "case_count": 1,
    "hit_count": 0,
    "miss_count": 1,
    "recall_at_5": 0.0,
}
assert diagnostics["degradation_summary"]["neo4j"] == {
    "case_count": 1,
    "case_ids": ["case-002"],
}
assert diagnostics["failure_summary"]["http_status"] == {
    "case_count": 1,
    "case_ids": ["case-003"],
}
```

Run the focused test. Expected: import failure because the helper does not exist.

- [ ] **Step 2: Implement deterministic aggregation**

In `scripts/benchmark.py`, add `case_id(case, index)` returning `case.get("id") or f"case-{index:03d}"`. During the search loop append one record per case with:

```python
{
    "case_id": case_id(case, index),
    "query": case["query"],
    "expected_recipe_ids": sorted(expected_ids(case)),
    "returned_recipe_ids": returned_ids_in_rank_order,
    "expected_intent": case["intent"],
    "actual_intent": payload.get("query_plan", {}).get("intent"),
    "hit": bool(expected.intersection(returned_ids_in_rank_order)),
    "degraded_components": sorted(
        payload.get("degradation", {}).get("unavailable_components") or []
    ),
    "failure_category": None,
}
```

For non-200 or `httpx.HTTPError`, append the same safe fields with empty results and `failure_category` equal to `http_status` or `http_error`; do not include exception text or headers. Aggregate sorted case IDs and stable intent/component keys.

- [ ] **Step 3: Add diagnostics to the report and remove the obsolete placeholder**

Merge `summarize_case_diagnostics(records)` into the returned report. Remove the warmed report's obsolete `"cold_start_ms": None`; cold-start now has its own measured report in Task 4. Preserve every other existing report field.

- [ ] **Step 4: Verify GREEN and regression compatibility**

```powershell
python -m pytest tests/test_benchmark.py -q -p no:cacheprovider
python -m ruff check scripts/benchmark.py tests/test_benchmark.py
```

Expected: benchmark tests PASS and Ruff reports no errors.

- [ ] **Step 5: Commit**

```powershell
git add scripts/benchmark.py tests/test_benchmark.py
git commit -m "feat: add benchmark diagnostics"
```

### Task 4: Independent cold-start measurement

**Files:**
- Create: `scripts/cold_start.py`
- Create: `tests/test_cold_start.py`

**Interfaces:**
- Produces: `measure_sample(command, base_url, timeout, query, *, popen_factory, client_factory, clock, sleeper) -> dict`.
- Produces: `summarize_samples(samples: list[dict]) -> dict`.
- CLI writes `Data/runtime/cold-start-report.json` by default.

- [ ] **Step 1: Write the four failing orchestration tests**

Use small fake process/client/clock objects; do not start a real server. Cover:

```python
def test_measure_sample_records_ready_and_first_search_latency(): ...
def test_measure_sample_reports_ready_timeout_and_terminates_process(): ...
def test_measure_sample_reports_process_exit_before_ready(): ...
def test_measure_sample_reports_first_search_http_failure(): ...
```

For the success case assert exactly:

```python
assert sample == {
    "status": "ok",
    "ready_ms": 250.0,
    "first_search_ms": 40.0,
}
assert process.terminated is True
```

For failures assert `status == "failed"`, a stage from `startup`, `ready`, or `search`, and an error type from a fixed allow-list; never assert raw exception text.

Run the focused file. Expected: import failure because `scripts.cold_start` does not exist.

- [ ] **Step 2: Implement one safely terminated sample**

`measure_sample()` must:

1. start `command` with stdin/stdout/stderr detached or redirected to `subprocess.DEVNULL`;
2. poll `/ready` until HTTP 200, process exit, or timeout;
3. issue one `POST /api/v1/search` with the fixed query;
4. record rounded millisecond durations;
5. always `terminate()`, wait briefly, then `kill()` only if needed;
6. return fixed safe error categories (`process_exit`, `ready_timeout`, `ready_http`, `search_http`, `client_error`).

Do not use a blocking sleep longer than 0.1 seconds while polling.

- [ ] **Step 3: Implement repeated samples and CLI**

For every sample, choose an available loopback port, then launch:

```python
[
    sys.executable,
    "-m",
    "cookqa.cli",
    "serve",
    "--host",
    "127.0.0.1",
    "--port",
    str(port),
]
```

CLI arguments:

```text
--samples 5
--timeout 30
--query 可乐鸡翅怎么做
--output Data/runtime/cold-start-report.json
```

The report contains `sample_count`, `success_count`, `failure_count`, `ready_samples`, `first_search_samples`, `samples`, and `targets.all_samples_succeeded`. Return process exit code 1 when any sample fails, after writing the report.

- [ ] **Step 4: Verify GREEN and lint**

```powershell
python -m pytest tests/test_cold_start.py -q -p no:cacheprovider
python -m ruff check scripts/cold_start.py tests/test_cold_start.py
```

Expected: all four paths PASS and Ruff reports no errors.

- [ ] **Step 5: Commit**

```powershell
git add scripts/cold_start.py tests/test_cold_start.py
git commit -m "feat: measure API cold starts"
```

### Task 5: P2A documentation and real acceptance

**Files:**
- Modify: `README.md`
- Modify: `docs/UNFINISHED.md`
- Runtime output only: `Data/runtime/benchmark-report.json`
- Runtime output only: `Data/runtime/cold-start-report.json`

**Interfaces:**
- Consumes: completed Tasks 1-4 and a running real CookQA service.
- Produces: reproducible commands and truthful P2A status; runtime JSON remains Git-ignored.

- [ ] **Step 1: Document the commands before claiming completion**

Add README commands for default tests, explicit integration tests, warmed benchmark, and cold-start measurement. State that integration requires an already running service with real Neo4j/Ollama and active 200-recipe indexes. Document that cold-start restarts only the API process.

- [ ] **Step 2: Run the default quality gate**

```powershell
$env:TEMP="$PWD\.tmp\pytest-temp"
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
python -m pytest -q -p no:cacheprovider -W error::DeprecationWarning
python -m ruff check .
python -m pip check
git diff --check
```

Expected: all commands PASS with no warnings.

- [ ] **Step 3: Run real-service integration and warmed benchmark**

With the service running and without printing credentials:

```powershell
python -m pytest -q -m integration -p no:cacheprovider
python scripts/benchmark.py `
  --base-url http://127.0.0.1:8000 `
  --warmups 3 `
  --timeout 30 `
  --output Data/runtime/benchmark-report.json
```

Expected: integration tests PASS; benchmark has 50 evaluated cases, Recall@5 at least 0.90, zero hard-filter violations, warmed search P95 at most 1000ms, first-token P95 at most 3000ms, and zero request/detail failures.

- [ ] **Step 4: Run the cold-start measurement**

Stop the manually running CookQA API first so each sample owns its process, while keeping Neo4j and Ollama running:

```powershell
python scripts/cold_start.py `
  --samples 5 `
  --timeout 30 `
  --output Data/runtime/cold-start-report.json
```

Expected: five successful samples, zero failures, valid P50/P95 ready and first-search summaries.

- [ ] **Step 5: Publish only measured P2A evidence**

Update `docs/UNFINISHED.md` with the exact fresh test count, warning count, integration result, benchmark metrics, and cold-start metrics. Mark only P2A complete; leave every P2B item open.

- [ ] **Step 6: Final P2A check and commit**

```powershell
git diff --check
git status --short
git add README.md docs/UNFINISHED.md
git commit -m "docs: record CookQA P2A acceptance"
```

Expected: `Data/` remains ignored and `tests/.sandbox-probe` remains the only unrelated untracked file.
