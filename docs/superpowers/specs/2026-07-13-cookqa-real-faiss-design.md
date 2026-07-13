# CookQA Real FAISS Index Design

## Goal

Replace the NumPy-backed dense index with a real FAISS exact inner-product index while keeping search behavior deterministic and readiness reporting truthful.

## Scope

- Replace `ExactVectorIndex` with `FaissVectorIndex`.
- Build a `faiss.IndexFlatIP` from L2-normalized recipe embeddings.
- Persist the binary index as `faiss.index` and recipe IDs as `faiss.ids.json`.
- Load and validate the index before the runtime can report ready.
- Update only the FAISS adapter, build pipeline, runtime loader, direct tests, and unfinished-status documentation.

The change does not add approximate search, legacy `.npz` compatibility, new retrieval abstractions, or unrelated refactoring.

## API and Storage

`FaissVectorIndex.build(recipe_ids, vectors)` validates a non-empty two-dimensional float matrix, rejects duplicate IDs and zero vectors, normalizes vectors with FAISS, and adds them to `faiss.IndexFlatIP`.

`search(vector, limit)` validates query shape and limit, normalizes the query, and returns recipe IDs with inner-product scores in FAISS result order. Invalid FAISS sentinel indices are never exposed.

`save(index_path, ids_path)` writes the FAISS binary index and a UTF-8 JSON ID list. The existing build staging directory provides the atomic publication boundary.

`load(index_path, ids_path)` rejects missing, unreadable, or inconsistent artifacts. It verifies:

- index type is usable for exact inner-product search;
- dimension is positive;
- `index.ntotal` equals the number of IDs;
- IDs are non-empty and unique.

## Failure Behavior

FAISS is imported lazily so the FastAPI process and `/health` can still start when the optional package is absent. Building or loading a dense index without FAISS raises a safe, explicit runtime error. The runtime catches load failures, exposes indexes as unavailable through `/ready`, and never silently falls back to NumPy while claiming FAISS is active.

## Integration Changes

- `BuildPipeline` writes `faiss.index` and `faiss.ids.json` and validates IDs and dimensions from `FaissVectorIndex`.
- `build_runtime` loads those two artifacts and constructs `FaissRetriever` with `FaissVectorIndex`.
- Production code and tests contain no remaining `ExactVectorIndex` or `faiss.npz` references.
- `pyproject.toml` keeps `faiss-cpu` as the existing `faiss` optional dependency; no new dependency is introduced.

## Tests and Acceptance

Tests are written before implementation and cover:

- real `faiss.IndexFlatIP` construction;
- nearest-neighbor search after normalization;
- binary save and reload;
- query dimension mismatch;
- zero vectors and duplicate IDs;
- ID-count mismatch and damaged artifacts;
- build-pipeline artifact names;
- runtime failure when FAISS artifacts cannot be loaded.

Acceptance requires the focused FAISS, builder, manifest, and runtime/API tests plus the full test suite to pass. A repository search must find no production references to `ExactVectorIndex` or `faiss.npz`. `/ready` must derive its FAISS state from the validated binary index.
