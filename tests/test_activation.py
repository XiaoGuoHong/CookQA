import json

import pytest

import cookqa.indexing.activation as activation
from cookqa.indexing.activation import (
    ActiveVersion,
    activate_version,
    read_active_version,
    swap_to_previous,
)


def test_missing_active_pointer_returns_none(tmp_path):
    assert read_active_version(tmp_path) is None


def test_activate_records_previous_version(tmp_path):
    activate_version(tmp_path, "v1", None)
    state = activate_version(tmp_path, "v2", "v1")
    saved = json.loads(
        (tmp_path / "runtime" / "active.json").read_text(encoding="utf-8")
    )

    assert state == ActiveVersion(version="v2", previous_version="v1")
    assert saved == {"version": "v2", "previous_version": "v1"}


def test_swap_to_previous_is_reversible(tmp_path):
    activate_version(tmp_path, "v2", "v1")

    assert swap_to_previous(tmp_path) == ActiveVersion(
        version="v1",
        previous_version="v2",
    )


def test_swap_rejects_missing_previous_version(tmp_path):
    activate_version(tmp_path, "v1", None)

    with pytest.raises(ValueError, match="没有可回滚的上一版本"):
        swap_to_previous(tmp_path)


def test_failed_atomic_replace_preserves_original_pointer(tmp_path, monkeypatch):
    activate_version(tmp_path, "v1", None)
    active_path = tmp_path / "runtime" / "active.json"
    original = active_path.read_bytes()

    def fail_replace(source, target):
        raise OSError("replace failed")

    monkeypatch.setattr(activation.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        activate_version(tmp_path, "v2", "v1")

    assert active_path.read_bytes() == original
    assert list((tmp_path / "runtime").glob("active.*.tmp")) == []
