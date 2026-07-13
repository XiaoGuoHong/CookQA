import numpy as np
import pytest

from cookqa.retrieval.faiss_store import ExactVectorIndex


def test_exact_vector_index_returns_cosine_nearest_neighbor():
    index = ExactVectorIndex.build(
        recipe_ids=["x", "y"],
        vectors=np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
    )

    results = index.search(np.array([0.9, 0.1], dtype=np.float32), limit=2)

    assert results[0][0] == "x"


def test_vector_dimension_mismatch_is_rejected():
    index = ExactVectorIndex.build(
        recipe_ids=["x"],
        vectors=np.array([[1.0, 0.0]], dtype=np.float32),
    )

    with pytest.raises(ValueError, match="维度"):
        index.search(np.array([1.0, 0.0, 0.0], dtype=np.float32), limit=1)
