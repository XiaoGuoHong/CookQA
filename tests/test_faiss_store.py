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
