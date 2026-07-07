import re
from pathlib import Path
from typing import Dict, Iterable, List

from .models import RecipeDocument


CATEGORY_BY_DIR = {
    "vegetable_dish": "素菜",
    "meat_dish": "荤菜",
    "aquatic": "水产",
    "breakfast": "早餐",
    "staple": "主食",
    "semi-finished": "半成品加工",
    "soup": "汤与粥",
    "dessert": "甜品",
    "drink": "饮品",
    "condiment": "酱料和其它材料",
}


def _clean_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^\s*[-*+]\s+", "", line)
    line = re.sub(r"^\s*\d+[.)、]\s*", "", line)
    return line.strip("` ").strip()


def _recipe_name_from_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            return re.sub(r"的做法$", "", title).strip() or fallback
    return fallback


def _sections(text: str) -> Dict[str, List[str]]:
    current = "intro"
    sections: Dict[str, List[str]] = {current: []}
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        if line.startswith("# "):
            continue
        sections.setdefault(current, []).append(line.rstrip())
    return sections


def _first_nonempty(lines: Iterable[str]) -> str:
    for line in lines:
        cleaned = _clean_line(line)
        if cleaned and not cleaned.startswith("预估"):
            return cleaned
    return ""


def _extract_metric(text: str, label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}[:：]\s*(.+)", text)
    return match.group(1).strip() if match else None


def _extract_list_items(lines: Iterable[str]) -> List[str]:
    items: List[str] = []
    for line in lines:
        cleaned = _clean_line(line)
        if not cleaned:
            continue
        if line.lstrip().startswith(("*", "-", "+")) or re.match(
            r"^\s*\d+[.)、]\s+", line
        ):
            items.append(cleaned)
    return items


def _category_from_path(relative: Path) -> str:
    parts = relative.parts
    if len(parts) >= 2 and parts[0] == "dishes":
        return CATEGORY_BY_DIR.get(parts[1], parts[1])
    return "未分类"


def parse_recipe_file(path: Path, root: Path) -> RecipeDocument:
    raw_text = path.read_text(encoding="utf-8")
    relative = path.relative_to(root).as_posix()
    section_map = _sections(raw_text)
    name = _recipe_name_from_title(raw_text, path.stem)

    return RecipeDocument(
        recipe_id=relative,
        name=name,
        category=_category_from_path(Path(relative)),
        source_path=relative,
        source_url=f"https://github.com/Anduin2017/HowToCook/blob/master/{relative}",
        description=_first_nonempty(section_map.get("intro", [])),
        difficulty=_extract_metric(raw_text, "预估烹饪难度"),
        calories=_extract_metric(raw_text, "预估卡路里"),
        ingredients=_extract_list_items(section_map.get("必备原料和工具", [])),
        tools=[],
        steps=_extract_list_items(section_map.get("操作", [])),
        notes=_extract_list_items(section_map.get("附加内容", [])),
        raw_text=raw_text,
    )


def load_recipes(root: Path) -> List[RecipeDocument]:
    dishes_root = root / "dishes"
    if not dishes_root.exists():
        return []
    return [
        parse_recipe_file(path, root)
        for path in sorted(dishes_root.rglob("*.md"))
        if path.is_file()
    ]
