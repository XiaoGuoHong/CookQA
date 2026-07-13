from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ActiveVersion:
    version: str
    previous_version: str | None = None


def read_active_version(data_dir: Path) -> ActiveVersion | None:
    path = data_dir / "runtime" / "active.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ActiveVersion(
        version=payload["version"],
        previous_version=payload.get("previous_version"),
    )


def activate_version(
    data_dir: Path,
    version: str,
    previous_version: str | None,
) -> ActiveVersion:
    state = ActiveVersion(version=version, previous_version=previous_version)
    runtime_dir = data_dir / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    temporary = runtime_dir / f"active.{uuid.uuid4().hex}.tmp"
    payload = {"version": state.version}
    if state.previous_version is not None:
        payload["previous_version"] = state.previous_version
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        os.replace(temporary, runtime_dir / "active.json")
    finally:
        temporary.unlink(missing_ok=True)
    return state


def swap_to_previous(data_dir: Path) -> ActiveVersion:
    current = read_active_version(data_dir)
    if current is None or current.previous_version is None:
        raise ValueError("没有可回滚的上一版本")
    return activate_version(
        data_dir,
        version=current.previous_version,
        previous_version=current.version,
    )
