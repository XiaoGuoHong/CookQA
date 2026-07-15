from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cookqa.indexing.activation import read_active_version
from cookqa.indexing.manifest import IndexManifest


@dataclass(frozen=True, slots=True)
class CleanupPlan:
    protected_versions: tuple[str, ...]
    missing_required_versions: tuple[str, ...]
    candidate_versions: tuple[str, ...]
    invalid_local_entries: tuple[str, ...]
    graph_only_versions: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CleanupResult:
    plan: CleanupPlan
    deleted_versions: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.as_dict(),
            "deleted_versions": self.deleted_versions,
        }


def build_cleanup_plan(
    data_dir: Path,
    graph_versions: set[str],
    explicit_keep: set[str] | None = None,
) -> CleanupPlan:
    protected = set(explicit_keep or set())
    required: set[str] = set()
    active = read_active_version(data_dir)
    if active is not None:
        required.add(active.version)
        if active.previous_version is not None:
            required.add(active.previous_version)
    protected.update(required)

    valid_local: set[str] = set()
    invalid_local: list[str] = []
    indexes_dir = data_dir / "indexes"
    if indexes_dir.is_dir():
        for path in sorted(indexes_dir.iterdir(), key=lambda item: item.name):
            try:
                manifest = IndexManifest.load(path / "index-manifest.json")
            except (OSError, ValueError):
                invalid_local.append(path.name)
                continue
            if not path.is_dir() or manifest.data_version != path.name:
                invalid_local.append(path.name)
                continue
            valid_local.add(path.name)

    candidates = valid_local - protected
    graph_only = graph_versions - valid_local - protected
    missing_required = required - valid_local
    return CleanupPlan(
        protected_versions=tuple(sorted(protected)),
        missing_required_versions=tuple(sorted(missing_required)),
        candidate_versions=tuple(sorted(candidates)),
        invalid_local_entries=tuple(sorted(invalid_local)),
        graph_only_versions=tuple(sorted(graph_only)),
    )


def append_operation_event(
    data_dir: Path,
    *,
    operation: str,
    source_version: str | None,
    target_version: str | None,
    result: str,
    error_category: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    runtime_dir = data_dir / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "operation": operation,
        "source_version": source_version,
        "target_version": target_version,
        "result": result,
    }
    if error_category is not None:
        payload["error_category"] = error_category
    if details is not None:
        payload["details"] = details
    with (runtime_dir / "index-operations.jsonl").open(
        "a", encoding="utf-8", newline="\n"
    ) as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
