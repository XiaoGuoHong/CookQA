# CookQA Real FAISS Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the NumPy-backed dense index with a real, validated `faiss.IndexFlatIP` exposed through the explicitly named `FaissVectorIndex` class.

**Architecture:** Keep the existing retrieval port and coordinator unchanged. The FAISS adapter owns vector normalization, exact inner-product search, binary index persistence, ID mapping persistence, and artifact validation; the builder publishes both artifacts from its staging directory, and runtime readiness depends on successfully loading them.

**Tech Stack:** Python 3.11+, NumPy, `faiss-cpu>=1.8,<2`, FastAPI runtime wiring, pytest, Ruff.

## Global Constraints

- Use `FaissVectorIndex`; do not retain an `ExactVectorIndex` compatibility alias.
- Use `faiss.IndexFlatIP` with L2-normalized recipe and query vectors.
- Persist `faiss.index` and `faiss.ids.json` separately; do not read or write `faiss.npz`.
- Import FAISS lazily so `/health` can still start when the optional package is missing.
- Missing or invalid FAISS artifacts make `/ready` unavailable; never fall back to NumPy while reporting FAISS as available.
- Do not change retrieval routing, RRF, Neo4j, Ollama, Web UI, or unrelated project structure.
- Do not log credentials, request headers, raw exception traces, or environment variable values.

---

## File Structure

- Modify `cookqa/retrieval/faiss_store.py`: own real FAISS construction, validation, persistence, loading, and dense retrieval.
- Modify `tests/test_faiss_store.py`: prove the adapter uses `IndexFlatIP` and rejects invalid inputs and artifacts.
- Modify `cookqa/indexing/builder.py`: publish the two FAISS artifacts from the existing staging directory.
- Modify `tests/test_builder.py`: verify real FAISS build artifacts and contents.
- Modify `cookqa/runtime.py`: load the two artifacts and use the renamed type.
- Create `tests/test_runtime.py`: prove an invalid FAISS load degrades runtime readiness without breaking process construction.
- Modify `docs/UNFINISHED.md`: record P0 FAISS completion and current verification evidence without claiming Neo4j, evaluation, or performance completion.

---

### Task 1: Implement and Validate `FaissVectorIndex`

**Files:**
- Modify: `tests/test_faiss_store.py`
- Modify: `cookqa/retrieval/faiss_store.py`

**Interfaces:**
- Consumes: `recipe_ids: list[str]`, `vectors: numpy.ndarray`, query vectors, `Path` objects for the index and ID mapping.
- Produces: `FaissVectorIndex.build(recipe_ids, vectors)`, `search(vector, limit)`, `save(index_path, ids_path)`, `load(index_path, ids_path)`, `recipe_ids`, `dimension`, and the wrapped `index`.

- [ ] **Step 1: Replace the NumPy adapter tests with real FAISS behavior tests**

Write `tests/test_faiss_store.py` as:

```python
import json

import faiss
import numpy as np
import pytest

from cookqa.retrieval.faiss_store import FaissVectorIndex


def build_index():
    return FaissVectorIndex.build(
        recipe_ids=["x", "y"],
        vectors=np.array([[1.0, 0.0], [0.0, 2.0]], dtype=np.float32),
    )


def test_builds_real_index_flat_ip_and_returns_cosine_nearest_neighbor():
    vector_index = build_index()

    assert isinstance(vector_index.index, faiss.IndexFlatIP)
    assert vector_index.index.ntotal == 2
    assert vector_index.search(np.array([0.9, 0.1], dtype=np.float32), limit=2)[0][0] == "x"


def test_binary_index_and_id_mapping_round_trip(tmp_path):
    vector_index = build_index()
    index_path = tmp_path / "faiss.index"
    ids_path = tmp_path / "faiss.ids.json"

    vector_index.save(index_path, ids_path)
    loaded = FaissVectorIndex.load(index_path, ids_path)

    assert loaded.recipe_ids == ["x", "y"]
    assert loaded.dimension == 2
    assert loaded.search(np.array([0.0, 1.0], dtype=np.float32), limit=1)[0][0] == "y"


def test_query_dimension_mismatch_is_rejected():
    with pytest.raises(ValueError, match="维度"):
        build_index().search(np.array([1.0, 0.0, 0.0], dtype=np.float32), limit=1)


def test_duplicate_recipe_ids_are_rejected():
    with pytest.raises(ValueError, match="重复"):
        FaissVectorIndex.build(
            ["x", "x"],
            np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        )


def test_zero_vectors_are_rejected():
    with pytest.raises(ValueError, match="零向量"):
        FaissVectorIndex.build(["x"], np.array([[0.0, 0.0]], dtype=np.float32))


def test_load_rejects_id_count_mismatch(tmp_path):
    index_path = tmp_path / "faiss.index"
    ids_path = tmp_path / "faiss.ids.json"
    build_index().save(index_path, ids_path)
    ids_path.write_text(json.dumps(["x"]), encoding="utf-8")

    with pytest.raises(ValueError, match="数量"):
        FaissVectorIndex.load(index_path, ids_path)


def test_load_rejects_damaged_binary_index(tmp_path):
    index_path = tmp_path / "faiss.index"
    ids_path = tmp_path / "faiss.ids.json"
    index_path.write_bytes(b"not-a-faiss-index")
    ids_path.write_text(json.dumps(["x"]), encoding="utf-8")

    with pytest.raises(RuntimeError, match="无法读取"):
        FaissVectorIndex.load(index_path, ids_path)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
$env:TEMP="$PWD\.tmp\pytest-temp"
$env:TMP=$env:TEMP
python -m pytest tests/test_faiss_store.py -q --basetemp .tmp\pytest-faiss-red -o cache_dir=.tmp\pytest-cache
```

Expected: collection fails because `FaissVectorIndex` does not exist.

- [ ] **Step 3: Replace the NumPy index with the minimal real FAISS implementation**

Rewrite `cookqa/retrieval/faiss_store.py` to provide this behavior while retaining `FaissRetriever`:

```python
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import numpy as np

from cookqa.models import QueryPlan, RankedCandidate
from cookqa.retrieval.ports import Embedder


def _require_faiss():
    try:
        import faiss
    except ImportError as exc:
        raise RuntimeError("FAISS 不可用，请安装 faiss-cpu") from exc
    return faiss


def _validate_recipe_ids(recipe_ids: list[str]) -> None:
    if not recipe_ids or any(not isinstance(item, str) or not item for item in recipe_ids):
        raise ValueError("recipe_ids 必须是非空字符串列表")
    if len(recipe_ids) != len(set(recipe_ids)):
        raise ValueError("recipe_ids 包含重复值")


def _as_matrix(vectors: np.ndarray, recipe_count: int) -> np.ndarray:
    array = np.asarray(vectors, dtype=np.float32)
    if array.ndim != 2 or array.shape[0] != recipe_count or array.shape[1] == 0:
        raise ValueError("向量矩阵形状与 recipe_ids 不一致")
    if not np.isfinite(array).all():
        raise ValueError("向量必须是有限数值")
    if np.any(np.linalg.norm(array, axis=1) == 0):
        raise ValueError("向量不能为零向量")
    return np.ascontiguousarray(array)


class FaissVectorIndex:
    def __init__(self, recipe_ids: list[str], index: Any):
        faiss = _require_faiss()
        _validate_recipe_ids(recipe_ids)
        if not isinstance(index, faiss.IndexFlatIP):
            raise ValueError("FAISS 索引必须是 IndexFlatIP")
        if int(index.d) <= 0:
            raise ValueError("FAISS 索引维度必须为正数")
        if int(index.ntotal) != len(recipe_ids):
            raise ValueError("FAISS 向量数量与 recipe_ids 数量不一致")
        self.recipe_ids = list(recipe_ids)
        self.index = index
        self.dimension = int(index.d)

    @classmethod
    def build(cls, recipe_ids: list[str], vectors: np.ndarray) -> "FaissVectorIndex":
        faiss = _require_faiss()
        _validate_recipe_ids(recipe_ids)
        array = _as_matrix(vectors, len(recipe_ids))
        faiss.normalize_L2(array)
        index = faiss.IndexFlatIP(array.shape[1])
        index.add(array)
        return cls(recipe_ids, index)

    def search(self, vector: np.ndarray, limit: int) -> list[tuple[str, float]]:
        if limit <= 0:
            raise ValueError("limit 必须大于 0")
        query = np.asarray(vector, dtype=np.float32)
        if query.ndim != 1 or query.shape[0] != self.dimension:
            raise ValueError("查询向量维度与索引不一致")
        query = _as_matrix(query.reshape(1, -1), 1)
        faiss = _require_faiss()
        faiss.normalize_L2(query)
        scores, indices = self.index.search(query, min(limit, len(self.recipe_ids)))
        return [
            (self.recipe_ids[int(index)], float(score))
            for score, index in zip(scores[0], indices[0], strict=True)
            if 0 <= int(index) < len(self.recipe_ids)
        ]

    def save(self, index_path: Path, ids_path: Path) -> None:
        faiss = _require_faiss()
        index_path.parent.mkdir(parents=True, exist_ok=True)
        ids_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(index_path))
        ids_path.write_text(
            json.dumps(self.recipe_ids, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, index_path: Path, ids_path: Path) -> "FaissVectorIndex":
        faiss = _require_faiss()
        try:
            index = faiss.read_index(str(index_path))
        except Exception as exc:
            raise RuntimeError("FAISS 索引无法读取") from exc
        try:
            recipe_ids = json.loads(ids_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("FAISS recipe_id 映射无法读取") from exc
        if not isinstance(recipe_ids, list):
            raise ValueError("FAISS recipe_id 映射格式无效")
        return cls(recipe_ids, index)


class FaissRetriever:
    name = "faiss"

    def __init__(
        self,
        index: FaissVectorIndex,
        embedder: Embedder,
        timeout_seconds: float = 0.75,
    ):
        self.index = index
        self.embedder = embedder
        self.timeout_seconds = timeout_seconds

    async def search(self, plan: QueryPlan, limit: int) -> list[RankedCandidate]:
        vector = await asyncio.wait_for(
            self.embedder.embed(plan.normalized_query), timeout=self.timeout_seconds
        )
        return [
            RankedCandidate(
                recipe_id=recipe_id,
                score=score,
                source=self.name,
                reasons=["语义相似"],
            )
            for recipe_id, score in self.index.search(
                np.asarray(vector, dtype=np.float32), limit
            )
        ]
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the Step 2 command again.

Expected: `7 passed`.

- [ ] **Step 5: Run Ruff on the adapter and test**

Run:

```powershell
python -m ruff check cookqa/retrieval/faiss_store.py tests/test_faiss_store.py
```

Expected: `All checks passed!`.

- [ ] **Step 6: Commit the adapter**

```powershell
git add cookqa/retrieval/faiss_store.py tests/test_faiss_store.py
git commit -m "feat: use real FAISS vector index"
```

---

### Task 2: Integrate FAISS Artifacts with Build and Runtime

**Files:**
- Modify: `tests/test_builder.py`
- Create: `tests/test_runtime.py`
- Modify: `cookqa/indexing/builder.py`
- Modify: `cookqa/runtime.py`

**Interfaces:**
- Consumes: `FaissVectorIndex.build`, `save(index_path, ids_path)`, and `load(index_path, ids_path)` from Task 1.
- Produces: build artifacts `faiss.index` and `faiss.ids.json`; `build_runtime(settings)` that becomes unavailable when either artifact fails validation.

- [ ] **Step 1: Update builder expectations and add the runtime degradation test**

In `tests/test_builder.py`, import FAISS, retain the graph writer used by the build, and replace the old `.npz` assertion with:

```python
import faiss


graph_writer = FakeGraphWriter()
result = asyncio.run(
    BuildPipeline(FakeEmbedder(), graph_writer).build(
        source_root=source,
        selection_path=selection,
        aliases_path=aliases,
        source_version="abc123",
        embedding_model="bge-m3",
        data_dir=data_dir,
    )
)

index_path = result.artifact_dir / "faiss.index"
ids_path = result.artifact_dir / "faiss.ids.json"
assert index_path.is_file()
assert ids_path.is_file()
assert faiss.read_index(str(index_path)).ntotal == 1
assert json.loads(ids_path.read_text(encoding="utf-8")) == list(graph_writer.ids)
```

Keep the existing active-version, BM25, processed-data, and manifest assertions.

Create `tests/test_runtime.py`:

```python
import asyncio
import json

import pytest

import cookqa.runtime as runtime
from cookqa.config import Settings


def test_invalid_faiss_artifact_makes_runtime_unavailable(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "active.json").write_text(
        json.dumps({"version": "v1"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime.IndexManifest, "load", staticmethod(lambda path: object()))
    monkeypatch.setattr(runtime, "_load_recipes", lambda path: {})
    monkeypatch.setattr(runtime.BM25Retriever, "load", staticmethod(lambda path: object()))

    def fail_load(index_path, ids_path):
        raise RuntimeError("FAISS 索引无法读取")

    monkeypatch.setattr(runtime.FaissVectorIndex, "load", staticmethod(fail_load))

    service, readiness, _ = runtime.build_runtime(Settings(data_dir=tmp_path))

    assert readiness.load_error == "运行数据未就绪: RuntimeError"
    with pytest.raises(RuntimeError, match="运行数据未就绪"):
        asyncio.run(service.search("番茄炒蛋"))
```

- [ ] **Step 2: Run the integration tests and verify RED**

Run:

```powershell
$env:TEMP="$PWD\.tmp\pytest-temp"
$env:TMP=$env:TEMP
python -m pytest tests/test_builder.py tests/test_runtime.py -q --basetemp .tmp\pytest-faiss-integration-red -o cache_dir=.tmp\pytest-cache
```

Expected: builder fails because `faiss.index` and `faiss.ids.json` are absent, and runtime test fails because it cannot patch `FaissVectorIndex` before the integration changes.

- [ ] **Step 3: Update the builder to publish real FAISS artifacts**

In `cookqa/indexing/builder.py`:

```python
from cookqa.retrieval.faiss_store import FaissVectorIndex
```

Replace the dense-index build and save block with:

```python
vector_index = FaissVectorIndex.build(recipe_ids, vectors)
vector_index.save(
    staging_dir / "faiss.index",
    staging_dir / "faiss.ids.json",
)
```

Keep manifest construction and cross-index validation unchanged; they consume `vector_index.recipe_ids` and `vector_index.dimension`.

- [ ] **Step 4: Update runtime loading and type annotations**

In `cookqa/runtime.py`, import `FaissVectorIndex` instead of `ExactVectorIndex`, change `RuntimeReadiness.vector_index` to `FaissVectorIndex | None`, and load:

```python
vector_index = FaissVectorIndex.load(
    artifact_dir / "faiss.index",
    artifact_dir / "faiss.ids.json",
)
```

Keep `FaissRetriever`, manifest validation, safe class-name-only load errors, and all non-FAISS runtime logic unchanged.

- [ ] **Step 5: Run focused integration tests and verify GREEN**

Run:

```powershell
$env:TEMP="$PWD\.tmp\pytest-temp"
$env:TMP=$env:TEMP
python -m pytest tests/test_faiss_store.py tests/test_builder.py tests/test_manifest.py tests/test_runtime.py -q --basetemp .tmp\pytest-faiss-integration -o cache_dir=.tmp\pytest-cache
```

Expected: `12 passed`.

- [ ] **Step 6: Run Ruff on all changed Python files**

```powershell
python -m ruff check cookqa/retrieval/faiss_store.py cookqa/indexing/builder.py cookqa/runtime.py tests/test_faiss_store.py tests/test_builder.py tests/test_runtime.py
```

Expected: `All checks passed!`.

- [ ] **Step 7: Commit build and runtime integration**

```powershell
git add cookqa/indexing/builder.py cookqa/runtime.py tests/test_builder.py tests/test_runtime.py
git commit -m "feat: load validated FAISS artifacts"
```

---

### Task 3: Update Status Documentation and Run Final Verification

**Files:**
- Modify: `docs/UNFINISHED.md`

**Interfaces:**
- Consumes: verified test output and repository searches from Tasks 1 and 2.
- Produces: accurate P0 status without changing the remaining Neo4j, comparison, integration, evaluation, or performance requirements.

- [ ] **Step 1: Prove the legacy implementation is gone**

Run:

```powershell
rg -n "ExactVectorIndex|faiss\.npz" cookqa tests
```

Expected: no matches and exit code `1`.

Run:

```powershell
rg -n "FaissVectorIndex|faiss\.index|faiss\.ids\.json|IndexFlatIP" cookqa tests
```

Expected: matches in the adapter, builder, runtime, and direct tests.

- [ ] **Step 2: Run the complete automated test suite**

```powershell
$env:TEMP="$PWD\.tmp\pytest-temp"
$env:TMP=$env:TEMP
python -m pytest -q --basetemp .tmp\pytest-real-faiss -o cache_dir=.tmp\pytest-cache
```

Expected: `55 passed, 1 warning`; the existing warning is the FastAPI TestClient compatibility warning.

- [ ] **Step 3: Run the full Ruff check**

```powershell
python -m ruff check .
```

Expected: `All checks passed!`.

- [ ] **Step 4: Update `docs/UNFINISHED.md` with verified evidence**

Make only these status changes:

- Change the current conclusion from “真实 FAISS …仍未闭环” to state that real FAISS is complete while Neo4j safe switching, recipe comparison, full local integration, evaluation, and performance remain open.
- Change section `4.1` to `### 4.1 使用真实 FAISS 索引（已完成）`.
- Replace the old NumPy `.npz` description with verified facts: `FaissVectorIndex`, `faiss.IndexFlatIP`, L2 normalization, `faiss.index`, `faiss.ids.json`, load-time dimension/count/ID validation, and explicit unavailable behavior.
- Record the focused and full test results from Steps 2 and 3 exactly.
- Check only the final checklist item `使用真实 FAISS 菜谱级索引`; leave every other completion checkbox unchanged.

- [ ] **Step 5: Run documentation and diff checks**

```powershell
rg -n "真实 FAISS|FaissVectorIndex|faiss.index|faiss.ids.json|55 passed" docs/UNFINISHED.md
git diff --check
git status --short
```

Expected: the document contains the verified evidence, `git diff --check` reports no errors, and status lists only the intended Task 3 documentation change plus the pre-existing untracked `tests/.sandbox-probe`.

- [ ] **Step 6: Commit documentation and push the completed slice**

```powershell
git add docs/UNFINISHED.md
git commit -m "docs: record real FAISS completion"
git push origin main
```

Expected: `main` advances by the three implementation commits and the remote push succeeds.
