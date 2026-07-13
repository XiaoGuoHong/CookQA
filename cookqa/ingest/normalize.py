from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import PurePosixPath

_SPACE_RE = re.compile(r"[\s　]+")
_TRAILING_PUNCTUATION_RE = re.compile(r"[：:，,。；;]+$")


def normalize_relative_path(relative_path: str) -> str:
    value = relative_path.replace("\\", "/").strip().lstrip("./")
    return PurePosixPath(value).as_posix().casefold()


def stable_recipe_id(relative_path: str) -> str:
    normalized = normalize_relative_path(relative_path)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def normalize_ingredient(raw_name: str, aliases: Mapping[str, str]) -> str:
    value = _SPACE_RE.sub("", raw_name)
    value = _TRAILING_PUNCTUATION_RE.sub("", value)
    return aliases.get(value, value)


def normalize_query_text(value: str) -> str:
    return _SPACE_RE.sub("", value.strip()).casefold()
