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
