import asyncio
import json

import pytest

from cookqa.indexing.activation import activate_version
from cookqa.indexing.builder import BuildPipeline
from cookqa.indexing.manifest import IndexManifest
from cookqa.indexing.operations import append_operation_event, build_cleanup_plan


class CleanupGraphWriter:
    def __init__(self, versions):
        self.versions = set(versions)
        self.deleted = []

    async def list_versions(self):
        return set(self.versions)

    async def delete_version(self, data_version):
        self.deleted.append(data_version)
        self.versions.remove(data_version)


def write_version(data_dir, version):
    artifact_dir = data_dir / "indexes" / version
    artifact_dir.mkdir(parents=True)
    IndexManifest(
        data_version=version,
        recipe_count=1,
        recipe_id_hash="hash",
        embedding_model="bge-m3",
        embedding_dimension=2,
        bm25_version="1",
        faiss_version="1",
        graph_version=version,
    ).save(artifact_dir / "index-manifest.json")
    return artifact_dir


def test_cleanup_plan_protects_active_previous_and_explicit_versions(tmp_path):
    data_dir = tmp_path / "Data"
    for version in ("active", "previous", "explicit", "old"):
        write_version(data_dir, version)
    (data_dir / "indexes" / "invalid").mkdir()
    activate_version(data_dir, "active", "previous")

    plan = build_cleanup_plan(
        data_dir,
        graph_versions={"active", "previous", "explicit", "old", "graph-only"},
        explicit_keep={"explicit"},
    )

    assert plan.protected_versions == ("active", "explicit", "previous")
    assert plan.candidate_versions == ("old",)
    assert plan.invalid_local_entries == ("invalid",)
    assert plan.graph_only_versions == ("graph-only",)
    assert plan.missing_required_versions == ()


def test_cleanup_history_is_dry_run_by_default_and_apply_is_scoped(tmp_path):
    data_dir = tmp_path / "Data"
    for version in ("active", "previous", "old"):
        write_version(data_dir, version)
    activate_version(data_dir, "active", "previous")
    writer = CleanupGraphWriter({"active", "previous", "old"})
    pipeline = BuildPipeline(embedder=None, graph_writer=writer)

    dry_run = asyncio.run(pipeline.cleanup_history(data_dir))

    assert dry_run.deleted_versions == ()
    assert writer.deleted == []
    assert (data_dir / "indexes" / "old").is_dir()

    applied = asyncio.run(pipeline.cleanup_history(data_dir, apply=True))

    assert applied.deleted_versions == ("old",)
    assert writer.deleted == ["old"]
    assert not (data_dir / "indexes" / "old").exists()
    events = [
        json.loads(line)
        for line in (data_dir / "runtime" / "index-operations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [event["operation"] for event in events] == ["cleanup_dry_run", "cleanup"]
    assert all(event["result"] == "success" for event in events)


def test_cleanup_apply_rejects_missing_active_pointer(tmp_path):
    data_dir = tmp_path / "Data"
    write_version(data_dir, "old")
    writer = CleanupGraphWriter({"old"})
    pipeline = BuildPipeline(embedder=None, graph_writer=writer)

    with pytest.raises(ValueError, match="缺少活动版本指针"):
        asyncio.run(pipeline.cleanup_history(data_dir, apply=True))

    assert writer.deleted == []
    assert (data_dir / "indexes" / "old").is_dir()


def test_cleanup_apply_rejects_missing_active_artifact(tmp_path):
    data_dir = tmp_path / "Data"
    write_version(data_dir, "old")
    activate_version(data_dir, "missing-active", None)
    writer = CleanupGraphWriter({"missing-active", "old"})
    pipeline = BuildPipeline(embedder=None, graph_writer=writer)

    dry_run = asyncio.run(pipeline.cleanup_history(data_dir))

    assert dry_run.plan.missing_required_versions == ("missing-active",)
    with pytest.raises(ValueError, match="受保护版本缺少有效本地 artifact"):
        asyncio.run(pipeline.cleanup_history(data_dir, apply=True))

    assert writer.deleted == []
    assert (data_dir / "indexes" / "old").is_dir()
    events = [
        json.loads(line)
        for line in (data_dir / "runtime" / "index-operations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert events[-1]["operation"] == "cleanup"
    assert events[-1]["result"] == "failed"


def test_operation_log_stores_safe_error_category_without_exception_text(tmp_path):
    data_dir = tmp_path / "Data"

    append_operation_event(
        data_dir,
        operation="rollback",
        source_version="v2",
        target_version="v1",
        result="failed",
        error_category="RuntimeError",
        details={"protected_versions": ["v2", "v1"]},
    )

    text = (data_dir / "runtime" / "index-operations.jsonl").read_text(
        encoding="utf-8"
    )
    event = json.loads(text)
    assert event["error_category"] == "RuntimeError"
    assert "exception" not in event
    assert "password" not in text.casefold()
