import pytest

from cookqa.indexing.manifest import (
    IndexManifest,
    ManifestMismatch,
    compute_id_hash,
    validate_manifest,
)


def manifest():
    return IndexManifest(
        data_version="abc",
        recipe_count=1,
        recipe_id_hash=compute_id_hash(["a"]),
        embedding_model="bge-m3",
        embedding_dimension=2,
        bm25_version="1",
        faiss_version="1",
        graph_version="abc",
    )


def test_manifest_rejects_mixed_recipe_ids():
    with pytest.raises(ManifestMismatch, match="recipe_id"):
        validate_manifest(
            manifest(),
            bm25_ids={"a"},
            faiss_ids={"a", "b"},
            graph_ids={"a"},
            embedding_dimension=2,
        )


def test_id_hash_is_order_independent():
    assert compute_id_hash(["b", "a"]) == compute_id_hash(["a", "b"])


def test_manifest_rejects_embedding_dimension_mismatch():
    with pytest.raises(ManifestMismatch, match="向量维度"):
        validate_manifest(
            manifest(),
            bm25_ids={"a"},
            faiss_ids={"a"},
            graph_ids={"a"},
            embedding_dimension=3,
        )
