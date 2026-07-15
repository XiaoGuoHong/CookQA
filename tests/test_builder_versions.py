import asyncio
import json
from pathlib import Path

import pytest

import cookqa.indexing.builder as builder_module
from cookqa.indexing.builder import BuildPipeline

FIXTURE = Path(__file__).parent / "fixtures" / "howtocook" / "sample.md"


def read_operation_events(data_dir):
    return [
        json.loads(line)
        for line in (data_dir / "runtime" / "index-operations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]


class FakeEmbedder:
    async def embed(self, text):
        return [1.0, float(len(text) % 7 + 1)]


class FakeGraphWriter:
    def __init__(self, fail_at=None):
        self.versions = {}
        self.fail_at = fail_at
        self.written = []
        self.deleted = []

    async def ensure_schema(self):
        if self.fail_at == "schema":
            raise RuntimeError("schema failed")

    async def write_version(self, recipes, data_version):
        self.written.append(data_version)
        self.versions[data_version] = {recipe.recipe_id for recipe in recipes}
        if self.fail_at == "write":
            raise RuntimeError("write failed")

    async def validate_version(self, recipes, data_version):
        if self.fail_at == "validate":
            raise ValueError("validation failed")
        return set(self.versions.get(data_version, set()))

    async def delete_version(self, data_version):
        self.deleted.append(data_version)
        self.versions.pop(data_version, None)

    async def list_versions(self):
        if self.fail_at == "cleanup":
            raise RuntimeError("cleanup failed")
        return set(self.versions)


def build_inputs(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "sample.md").write_text(
        FIXTURE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    selection = tmp_path / "selection.txt"
    selection.write_text("sample.md\n", encoding="utf-8")
    aliases = tmp_path / "aliases.json"
    aliases.write_text('{"西红柿": "番茄"}', encoding="utf-8")
    return source, selection, aliases, tmp_path / "Data"


def run_build(tmp_path, writer):
    source, selection, aliases, data_dir = build_inputs(tmp_path)
    result = asyncio.run(
        BuildPipeline(FakeEmbedder(), writer).build(
            source_root=source,
            selection_path=selection,
            aliases_path=aliases,
            source_version="abc123",
            embedding_model="bge-m3",
            data_dir=data_dir,
        )
    )
    return result, data_dir


def run_second_build(tmp_path, writer, data_dir):
    source = tmp_path / "source"
    selection = tmp_path / "selection.txt"
    aliases = tmp_path / "aliases.json"
    return asyncio.run(
        BuildPipeline(FakeEmbedder(), writer).build(
            source_root=source,
            selection_path=selection,
            aliases_path=aliases,
            source_version="abc123",
            embedding_model="bge-m3",
            data_dir=data_dir,
        )
    )


@pytest.mark.parametrize("fail_at", ["write", "validate"])
def test_failed_candidate_preserves_active_version(tmp_path, fail_at):
    writer = FakeGraphWriter()
    first, data_dir = run_build(tmp_path, writer)
    active_path = data_dir / "runtime" / "active.json"
    original = active_path.read_bytes()
    writer.fail_at = fail_at

    with pytest.raises((RuntimeError, ValueError)):
        run_second_build(tmp_path, writer, data_dir)

    assert active_path.read_bytes() == original
    assert writer.deleted[-1] == writer.written[-1]
    assert first.manifest.data_version in writer.versions


def test_schema_failure_preserves_active_version(tmp_path):
    writer = FakeGraphWriter()
    first, data_dir = run_build(tmp_path, writer)
    active_path = data_dir / "runtime" / "active.json"
    original = active_path.read_bytes()
    written_before = list(writer.written)
    writer.fail_at = "schema"

    with pytest.raises(RuntimeError, match="schema failed"):
        run_second_build(tmp_path, writer, data_dir)

    assert active_path.read_bytes() == original
    assert writer.written == written_before
    assert first.manifest.data_version in writer.versions


def test_activation_failure_preserves_old_version(tmp_path, monkeypatch):
    writer = FakeGraphWriter()
    first, data_dir = run_build(tmp_path, writer)
    active_path = data_dir / "runtime" / "active.json"
    original = active_path.read_bytes()

    def fail_activation(data_dir, version, previous_version):
        raise OSError("switch failed")

    monkeypatch.setattr(builder_module, "activate_version", fail_activation)

    with pytest.raises(OSError, match="switch failed"):
        run_second_build(tmp_path, writer, data_dir)

    assert active_path.read_bytes() == original
    assert writer.deleted[-1] == writer.written[-1]
    assert first.manifest.data_version in writer.versions
    event = read_operation_events(data_dir)[-1]
    assert event["operation"] == "activate"
    assert event["result"] == "failed"
    assert event["error_category"] == "OSError"


def test_successful_build_retains_current_and_previous(tmp_path):
    writer = FakeGraphWriter()
    first, data_dir = run_build(tmp_path, writer)
    second = run_second_build(tmp_path, writer, data_dir)

    assert first.manifest.data_version != second.manifest.data_version
    assert set(writer.versions) == {
        first.manifest.data_version,
        second.manifest.data_version,
    }


def test_automatic_cleanup_deletes_only_versions_older_than_previous(tmp_path):
    writer = FakeGraphWriter()
    first, data_dir = run_build(tmp_path, writer)
    second = run_second_build(tmp_path, writer, data_dir)
    third = run_second_build(tmp_path, writer, data_dir)

    assert writer.deleted[-1] == first.manifest.data_version
    assert set(writer.versions) == {
        second.manifest.data_version,
        third.manifest.data_version,
    }


def test_cleanup_failure_does_not_undo_activation(tmp_path):
    writer = FakeGraphWriter()
    first, data_dir = run_build(tmp_path, writer)
    writer.fail_at = "cleanup"

    second = run_second_build(tmp_path, writer, data_dir)
    active = builder_module.read_active_version(data_dir)

    assert active.version == second.manifest.data_version
    assert active.previous_version == first.manifest.data_version
    event = read_operation_events(data_dir)[-1]
    assert event["operation"] == "cleanup"
    assert event["result"] == "failed"


def test_rollback_validates_and_swaps_versions(tmp_path):
    writer = FakeGraphWriter()
    first, data_dir = run_build(tmp_path, writer)
    second = run_second_build(tmp_path, writer, data_dir)

    result = asyncio.run(BuildPipeline(FakeEmbedder(), writer).rollback(data_dir))
    active = builder_module.read_active_version(data_dir)

    assert result.manifest.data_version == first.manifest.data_version
    assert active.version == first.manifest.data_version
    assert active.previous_version == second.manifest.data_version
    event = read_operation_events(data_dir)[-1]
    assert event["operation"] == "rollback"
    assert event["result"] == "success"


def test_failed_rollback_validation_preserves_current_version(tmp_path):
    writer = FakeGraphWriter()
    _, data_dir = run_build(tmp_path, writer)
    second = run_second_build(tmp_path, writer, data_dir)
    active_path = data_dir / "runtime" / "active.json"
    original = active_path.read_bytes()
    writer.fail_at = "validate"

    with pytest.raises(ValueError, match="validation failed"):
        asyncio.run(BuildPipeline(FakeEmbedder(), writer).rollback(data_dir))

    assert active_path.read_bytes() == original
    assert builder_module.read_active_version(data_dir).version == second.manifest.data_version
    event = read_operation_events(data_dir)[-1]
    assert event["operation"] == "rollback"
    assert event["result"] == "failed"
