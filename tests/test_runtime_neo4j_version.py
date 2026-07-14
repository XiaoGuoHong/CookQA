import json
import sys
from types import SimpleNamespace

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


def test_runtime_scopes_neo4j_retriever_to_manifest_version(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "active.json").write_text(
        json.dumps({"version": "v2", "previous_version": "v1"}),
        encoding="utf-8",
    )
    manifest = IndexManifest(
        data_version="v2",
        recipe_count=1,
        recipe_id_hash="hash",
        embedding_model="bge-m3",
        embedding_dimension=2,
        bm25_version="1",
        faiss_version="1",
        graph_version="v2",
    )
    recipe = Recipe(
        recipe_id="r1",
        name="番茄炒蛋",
        ingredients=[Ingredient(name="番茄", raw="番茄")],
        source_path="dishes/tomato.md",
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
    monkeypatch.setattr(runtime, "FaissRetriever", lambda *args: FakeRetriever("faiss"))
    fake_graph_database = SimpleNamespace(driver=lambda *args, **kwargs: object())
    monkeypatch.setitem(
        sys.modules,
        "neo4j",
        SimpleNamespace(GraphDatabase=fake_graph_database),
    )

    def capture_retriever(driver, data_version):
        captured["data_version"] = data_version
        return FakeRetriever("neo4j")

    monkeypatch.setattr(runtime, "Neo4jRetriever", capture_retriever)

    runtime.build_runtime(Settings(data_dir=tmp_path, neo4j_password="placeholder"))

    assert captured["data_version"] == "v2"
