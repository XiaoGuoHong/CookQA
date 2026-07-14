import json

import cookqa.runtime as runtime
from cookqa.config import Settings
from cookqa.indexing.manifest import IndexManifest
from cookqa.models import Ingredient, Recipe


class FakeRetriever:
    def __init__(self, name):
        self.name = name
        self.recipe_ids = ["r1"]


class FakeVectorIndex:
    recipe_ids = ["r1"]
    dimension = 2


def test_runtime_passes_recipe_name_to_id_mapping_to_faiss(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "active.json").write_text(
        json.dumps({"version": "v1"}),
        encoding="utf-8",
    )
    manifest = IndexManifest(
        data_version="v1",
        recipe_count=1,
        recipe_id_hash="hash",
        embedding_model="bge-m3",
        embedding_dimension=2,
        bm25_version="1",
        faiss_version="1",
        graph_version="v1",
    )
    recipe = Recipe(
        recipe_id="r1",
        name="Reference Recipe",
        aliases=["Reference Alias"],
        ingredients=[Ingredient(name="salt", raw="salt")],
        source_path="dishes/reference.md",
        source_version="abc",
    )
    captured = {}

    monkeypatch.setattr(runtime.IndexManifest, "load", staticmethod(lambda path: manifest))
    monkeypatch.setattr(runtime, "_load_recipes", lambda path: {"r1": recipe})
    monkeypatch.setattr(
        runtime.BM25Retriever,
        "load",
        staticmethod(lambda path: FakeRetriever("bm25")),
    )
    monkeypatch.setattr(
        runtime.FaissVectorIndex,
        "load",
        staticmethod(lambda index_path, ids_path: FakeVectorIndex()),
    )

    def capture_faiss(index, embedder, timeout_seconds, reference_recipe_ids):
        captured["reference_recipe_ids"] = reference_recipe_ids
        return FakeRetriever("faiss")

    monkeypatch.setattr(runtime, "FaissRetriever", capture_faiss)

    runtime.build_runtime(Settings(data_dir=tmp_path))

    assert captured["reference_recipe_ids"] == {
        "Reference Recipe": "r1",
        "Reference Alias": "r1",
    }
