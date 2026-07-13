from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from cookqa.ingest.normalize import normalize_ingredient, stable_recipe_id
from cookqa.models import FieldEvidence, Ingredient, Recipe


class RecipeParseError(ValueError):
    """Raised when a selected recipe cannot be parsed deterministically."""


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
_STEP_RE = re.compile(r"^\s*(?:\d+[.)、]|[-*+])\s+(.+?)\s*$")
_AMOUNT_RE = re.compile(
    r"(?P<amount>\d+(?:\.\d+)?|半|少许|适量)\s*(?P<unit>克|千克|公斤|斤|两|毫升|升|个|只|枚|勺|茶匙|汤匙|片|根|块|颗|瓣|把|碗|杯)?"
)
_DURATION_RE = re.compile(r"(?:烹饪|制作|总)?\s*(?:时间|耗时)\s*[：:]?\s*(\d+)\s*分钟")
_DIFFICULTY_RE = re.compile(r"难度\s*[：:]?\s*([^\s，,。]+)")


def _section_name(heading: str) -> str | None:
    value = heading.strip().casefold()
    if any(token in value for token in ("原料", "材料", "食材")):
        return "ingredients"
    if any(token in value for token in ("操作", "步骤", "做法")):
        return "steps"
    if any(token in value for token in ("计算", "信息", "参数")):
        return "metadata"
    return None


def _ingredient_from_line(raw: str, aliases: Mapping[str, str]) -> Ingredient:
    cleaned = raw.strip().strip("。；;")
    amount_match = _AMOUNT_RE.search(cleaned)
    name_part = cleaned[: amount_match.start()].strip(" ：:") if amount_match else cleaned
    name = normalize_ingredient(name_part, aliases)
    if not name:
        raise ValueError(f"无法提取食材名称: {raw}")
    amount: float | None = None
    unit: str | None = None
    if amount_match:
        amount_text = amount_match.group("amount")
        if amount_text.replace(".", "", 1).isdigit():
            amount = float(amount_text)
        elif amount_text == "半":
            amount = 0.5
        unit = amount_match.group("unit")
    optional = "可选" in cleaned or "按需" in cleaned
    return Ingredient(name=name, raw=cleaned, amount=amount, unit=unit, optional=optional)


def _infer_tags(text: str) -> tuple[list[str], list[FieldEvidence]]:
    rules = {
        "辣": ("辣椒", "小米椒", "豆瓣酱", "辣"),
        "快手": ("10 分钟", "15 分钟", "二十分钟", "20 分钟"),
        "少油": ("少油", "少量油"),
    }
    tags: list[str] = []
    evidence: list[FieldEvidence] = []
    for tag, keywords in rules.items():
        matched = next((keyword for keyword in keywords if keyword in text), None)
        if matched:
            tags.append(tag)
            evidence.append(
                FieldEvidence(field=f"tag:{tag}", source="rule", confidence=0.8, basis=matched)
            )
    return tags, evidence


def parse_recipe(
    path: Path,
    source_root: Path,
    source_version: str,
    aliases: Mapping[str, str],
) -> Recipe:
    try:
        relative_path = path.resolve().relative_to(source_root.resolve()).as_posix()
    except ValueError as exc:
        raise RecipeParseError(f"{path}: 文件不在数据源根目录内") from exc

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    name: str | None = None
    current_section: str | None = None
    ingredients: list[Ingredient] = []
    steps: list[str] = []
    metadata_lines: list[str] = []
    summary_lines: list[str] = []

    for line in lines:
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()
            if level == 1 and name is None:
                name = heading
            current_section = _section_name(heading)
            continue

        stripped = line.strip()
        if not stripped:
            continue
        if current_section == "ingredients":
            bullet = _BULLET_RE.match(line)
            if bullet:
                try:
                    ingredients.append(_ingredient_from_line(bullet.group(1), aliases))
                except ValueError as exc:
                    raise RecipeParseError(f"{path.name}: {exc}") from exc
        elif current_section == "steps":
            step = _STEP_RE.match(line)
            if step:
                steps.append(step.group(1).strip())
        elif current_section == "metadata":
            metadata_lines.append(stripped.lstrip("-*+ "))
        elif name is not None and not stripped.startswith(("!", "[")):
            summary_lines.append(stripped)

    if not name or not ingredients or not steps:
        missing = [
            label
            for label, value in (("菜名", name), ("食材", ingredients), ("步骤", steps))
            if not value
        ]
        raise RecipeParseError(f"{path.name}: 缺少必要字段: {', '.join(missing)}")

    metadata_text = "\n".join(metadata_lines)
    duration_match = _DURATION_RE.search(metadata_text)
    difficulty_match = _DIFFICULTY_RE.search(metadata_text)
    tags, inferred_evidence = _infer_tags(text)
    evidence = list(inferred_evidence)
    if duration_match:
        evidence.append(FieldEvidence(field="duration_minutes", source="source", confidence=1.0))
    if difficulty_match:
        evidence.append(FieldEvidence(field="difficulty", source="source", confidence=1.0))

    return Recipe(
        recipe_id=stable_recipe_id(relative_path),
        name=name,
        categories=[path.parent.name] if path.parent != source_root else [],
        summary=" ".join(summary_lines) or None,
        ingredients=ingredients,
        difficulty=difficulty_match.group(1) if difficulty_match else None,
        duration_minutes=int(duration_match.group(1)) if duration_match else None,
        steps=steps,
        tags=tags,
        evidence=evidence,
        source_path=relative_path,
        source_version=source_version,
    )
