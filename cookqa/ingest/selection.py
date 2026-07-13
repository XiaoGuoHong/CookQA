from __future__ import annotations

from pathlib import Path

from cookqa.ingest.normalize import normalize_relative_path


def load_selection(path: Path) -> list[str]:
    entries: list[str] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        normalized = normalize_relative_path(line)
        if normalized in seen:
            raise ValueError(f"选择清单第 {line_number} 行包含重复路径: {line}")
        seen.add(normalized)
        entries.append(line.replace("\\", "/"))
    if not entries:
        raise ValueError("选择清单不能为空")
    return entries


def validate_selection(source_root: Path, entries: list[str]) -> list[Path]:
    source_root = source_root.resolve()
    resolved: list[Path] = []
    missing: list[str] = []
    for entry in entries:
        path = (source_root / entry).resolve()
        try:
            path.relative_to(source_root)
        except ValueError as exc:
            raise ValueError(f"选择路径越过数据源根目录: {entry}") from exc
        if not path.is_file():
            missing.append(entry)
        else:
            resolved.append(path)
    if missing:
        raise FileNotFoundError("选择清单中的文件不存在: " + ", ".join(missing))
    return resolved
