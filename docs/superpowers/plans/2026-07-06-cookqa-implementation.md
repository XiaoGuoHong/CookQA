# CookQA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable FastAPI version of CookQA, a Docker-deployable Chinese recipe GraphRAG service based on HowToCook, FAISS, and Ollama.

**Architecture:** Replace the old BaseQA customer-service prototype with a focused `cookqa` package. Keep the system API-first: ingestion, parsing, graph relations, vector indexes, retrieval, and answer generation live behind FastAPI endpoints that can feed a future Web frontend. Keep tests fixture-based so unit and API tests do not require live Ollama or network access.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, Uvicorn, FAISS CPU, NumPy, HTTPX, pytest, Docker, Ollama `bge-m3`, Ollama `gpt-oss:120b-cloud`.

## Global Constraints

- Project path: `D:\WorkSpace\Code\Project100\CookQA`.
- Product names: Chinese name `食神`, English/project name `CookQA`.
- FastAPI-first backend; no full Web frontend in this implementation.
- Docker deployment is part of the first implementation.
- Ollama models are external and configured by `OLLAMA_BASE_URL`; do not copy model files into the app image.
- First implementation includes both recipe-level and step-level FAISS indexes.
- Normal tests must use local fixtures and must not require live Ollama, network access, or full HowToCook data.
- The local folder is not currently a git repository; skip commit steps until the folder is initialized or replaced with a clean clone of `https://github.com/XiaoGuoHong/CookQA.git`.

---

## File Structure

- Create `cookqa/__init__.py`: package marker and version.
- Create `cookqa/config.py`: environment-backed settings and path resolution.
- Create `cookqa/models.py`: shared Pydantic models for recipes, indexes, retrieval, and chat.
- Create `cookqa/parser.py`: Markdown recipe parser for HowToCook files.
- Create `cookqa/graph.py`: lightweight local relation graph builder and matcher.
- Create `cookqa/ollama_client.py`: embedding and chat client wrappers with clean failure modes.
- Create `cookqa/index_store.py`: FAISS index build/load/search code and JSON payload storage.
- Create `cookqa/retrieval.py`: intent detection, graph/vector/lexical merging, ranking, and recommendation shaping.
- Create `cookqa/generation.py`: grounded answer generation and template fallback.
- Create `cookqa/service.py`: orchestration facade used by API and CLI.
- Replace `api/schemas.py`: API request/response schemas for CookQA.
- Replace `api/app.py`: FastAPI app with health, chat, search, detail, and rebuild endpoints.
- Replace `main.py`: local CLI for chat and index rebuild.
- Replace `requirements.txt`: CookQA runtime/test dependencies.
- Replace `README.md`: setup, local run, indexing, Docker, and API examples.
- Create `Dockerfile`: app image for FastAPI.
- Create `docker-compose.yml`: local deployment with mounted data and external Ollama URL.
- Create `.dockerignore`: keep caches, indexes, logs, and local data out of the image.
- Create `tests/fixtures/howtocook/...`: tiny HowToCook-like Markdown dataset.
- Replace old tests with `tests/test_parser.py`, `tests/test_graph.py`, `tests/test_retrieval.py`, and `tests/test_api.py`.

Old `faq_qa/`, `rag_qa/`, `router/`, `common/`, and `base/` modules can remain on disk for archival context, but the new app must not import them. Remove or ignore old tests that assert BaseQA behavior.

---

### Task 1: Shared Models And Configuration

**Files:**
- Create: `cookqa/__init__.py`
- Create: `cookqa/config.py`
- Create: `cookqa/models.py`
- Modify: `requirements.txt`
- Test: `tests/test_config_models.py`

**Interfaces:**
- Produces: `CookQASettings.from_env() -> CookQASettings`
- Produces: `RecipeDocument`, `RecipeChunk`, `Recommendation`, `ChatResult`
- Consumes: none

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_models.py`:

```python
from pathlib import Path

from cookqa.config import CookQASettings
from cookqa.models import RecipeDocument


def test_settings_from_env_uses_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setenv("COOKQA_DATA_DIR", str(tmp_path / "data"))

    settings = CookQASettings.from_env()

    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.embedding_model == "bge-m3"
    assert settings.chat_model == "gpt-oss:120b-cloud"
    assert settings.data_dir == tmp_path / "data"
    assert settings.parsed_recipes_path == tmp_path / "data" / "parsed" / "recipes.json"
    assert settings.recipe_index_path == tmp_path / "data" / "indexes" / "recipes.faiss"
    assert settings.step_index_path == tmp_path / "data" / "indexes" / "steps.faiss"


def test_recipe_document_builds_search_text():
    recipe = RecipeDocument(
        recipe_id="dishes/vegetable_dish/西红柿炒鸡蛋.md",
        name="西红柿炒鸡蛋",
        category="素菜",
        source_path="dishes/vegetable_dish/西红柿炒鸡蛋.md",
        source_url=None,
        description="酸甜开胃的家常菜",
        difficulty="★★",
        calories="252 大卡",
        ingredients=["西红柿", "鸡蛋", "盐"],
        tools=[],
        steps=["炒鸡蛋", "炒西红柿", "合炒"],
        notes=["可以加葱花"],
        raw_text="# 西红柿炒鸡蛋的做法",
    )

    assert "西红柿炒鸡蛋" in recipe.search_text()
    assert "西红柿 鸡蛋 盐" in recipe.search_text()
    assert recipe.summary_steps() == ["炒鸡蛋", "炒西红柿", "合炒"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd D:\WorkSpace\Code\Project100\CookQA
python -m pytest tests/test_config_models.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'cookqa'`.

- [ ] **Step 3: Implement models and settings**

Create `cookqa/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `cookqa/config.py`:

```python
import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CookQASettings:
    project_root: Path
    data_dir: Path
    howtocook_path: Path
    ollama_base_url: str
    embedding_model: str
    chat_model: str
    top_k: int
    min_score: float
    enable_rebuild_api: bool

    @classmethod
    def from_env(cls) -> "CookQASettings":
        data_dir = Path(os.getenv("COOKQA_DATA_DIR", PROJECT_ROOT / "data")).resolve()
        return cls(
            project_root=PROJECT_ROOT,
            data_dir=data_dir,
            howtocook_path=Path(
                os.getenv("HOWTOCOOK_PATH", data_dir / "HowToCook")
            ).resolve(),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            embedding_model=os.getenv("OLLAMA_EMBEDDING_MODEL", "bge-m3"),
            chat_model=os.getenv("OLLAMA_CHAT_MODEL", "gpt-oss:120b-cloud"),
            top_k=int(os.getenv("COOKQA_TOP_K", "5")),
            min_score=float(os.getenv("COOKQA_MIN_SCORE", "0.15")),
            enable_rebuild_api=os.getenv("COOKQA_ENABLE_REBUILD_API", "true").lower()
            in {"1", "true", "yes", "on"},
        )

    @property
    def parsed_dir(self) -> Path:
        return self.data_dir / "parsed"

    @property
    def graph_dir(self) -> Path:
        return self.data_dir / "graph"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "indexes"

    @property
    def parsed_recipes_path(self) -> Path:
        return self.parsed_dir / "recipes.json"

    @property
    def graph_path(self) -> Path:
        return self.graph_dir / "relations.json"

    @property
    def recipe_index_path(self) -> Path:
        return self.index_dir / "recipes.faiss"

    @property
    def recipe_payload_path(self) -> Path:
        return self.index_dir / "recipes.payload.json"

    @property
    def step_index_path(self) -> Path:
        return self.index_dir / "steps.faiss"

    @property
    def step_payload_path(self) -> Path:
        return self.index_dir / "steps.payload.json"
```

Create `cookqa/models.py`:

```python
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


QueryMode = Literal["dish_lookup", "ingredient_exploration", "missing_or_fictional", "general"]


class RecipeDocument(BaseModel):
    recipe_id: str
    name: str
    category: str
    source_path: str
    source_url: Optional[str] = None
    description: str = ""
    difficulty: Optional[str] = None
    calories: Optional[str] = None
    ingredients: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    raw_text: str = ""

    def search_text(self) -> str:
        parts = [
            self.name,
            self.category,
            self.description,
            " ".join(self.ingredients),
            " ".join(self.tools),
            " ".join(self.steps),
            " ".join(self.notes),
        ]
        return "\n".join(part for part in parts if part).strip()

    def summary_steps(self, limit: int = 5) -> List[str]:
        return self.steps[:limit]


class RecipeChunk(BaseModel):
    chunk_id: str
    recipe_id: str
    name: str
    source_path: str
    text: str
    kind: Literal["recipe", "step"]
    ordinal: int = 0


class Recommendation(BaseModel):
    recipe_id: str
    name: str
    score: float
    match_reason: str
    ingredients: List[str] = Field(default_factory=list)
    summary_steps: List[str] = Field(default_factory=list)
    source_path: str
    source_url: Optional[str] = None
    graph_matches: List[str] = Field(default_factory=list)


class SourceRef(BaseModel):
    recipe_id: str
    name: str
    source_path: str
    source_url: Optional[str] = None


class ChatResult(BaseModel):
    answer: str
    mode: QueryMode
    recommendations: List[Recommendation]
    sources: List[SourceRef]
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

Modify `requirements.txt`:

```text
fastapi>=0.110.0
uvicorn>=0.27.0
pydantic>=2.6.0
httpx>=0.26.0
numpy>=1.26.0
faiss-cpu>=1.8.0
pytest>=8.0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_config_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit or record changes**

If the folder has been initialized as a Git repository:

```powershell
git add cookqa requirements.txt tests/test_config_models.py
git commit -m "feat: add CookQA core models and settings"
```

If it is still not a Git repository, record the changed files in the task review notes.

---

### Task 2: HowToCook Markdown Parser

**Files:**
- Create: `cookqa/parser.py`
- Create: `tests/fixtures/howtocook/dishes/vegetable_dish/西红柿炒鸡蛋.md`
- Create: `tests/fixtures/howtocook/dishes/meat_dish/水煮牛肉/水煮牛肉.md`
- Test: `tests/test_parser.py`

**Interfaces:**
- Consumes: `RecipeDocument`
- Produces: `parse_recipe_file(path: Path, root: Path) -> RecipeDocument`
- Produces: `load_recipes(root: Path) -> list[RecipeDocument]`

- [ ] **Step 1: Write the failing tests and fixtures**

Create `tests/fixtures/howtocook/dishes/vegetable_dish/西红柿炒鸡蛋.md`:

```markdown
# 西红柿炒鸡蛋的做法

酸甜开胃的家常菜。

预估烹饪难度：★★

预估卡路里：252 大卡

## 必备原料和工具

* 西红柿
* 鸡蛋
* 食用油
* 盐

## 计算

* 西红柿 = 1 个 * 份数
* 鸡蛋 = 1.5 个 * 份数

## 操作

1. 西红柿洗净切块。
2. 鸡蛋打散。
3. 先炒鸡蛋，再炒西红柿。
4. 合炒后加盐出锅。

## 附加内容

* 可以加葱花。
```

Create `tests/fixtures/howtocook/dishes/meat_dish/水煮牛肉/水煮牛肉.md`:

```markdown
# 水煮牛肉的做法

川菜经典麻辣味型。

预估烹饪难度：★★★

预估卡路里：431 大卡

## 必备原料和工具

* 牛肉
* 豆芽
* 鸡蛋
* 豆瓣酱
* 姜
* 蒜

## 操作

1. 牛肉洗干净切片。
2. 加鸡蛋、淀粉、料酒腌制。
3. 锅里倒油，加入豆瓣酱、姜、蒜。
4. 倒入开水，煮成红汤。
5. 豆芽焯熟后铺入碗底。
6. 牛肉片放进红汤中煮熟。
7. 撒辣椒粉后淋热油。
```

Create `tests/test_parser.py`:

```python
from pathlib import Path

from cookqa.parser import load_recipes, parse_recipe_file


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "howtocook"


def test_parse_recipe_file_extracts_structured_fields():
    recipe_path = FIXTURE_ROOT / "dishes" / "vegetable_dish" / "西红柿炒鸡蛋.md"

    recipe = parse_recipe_file(recipe_path, FIXTURE_ROOT)

    assert recipe.recipe_id == "dishes/vegetable_dish/西红柿炒鸡蛋.md"
    assert recipe.name == "西红柿炒鸡蛋"
    assert recipe.category == "素菜"
    assert recipe.description == "酸甜开胃的家常菜。"
    assert recipe.difficulty == "★★"
    assert recipe.calories == "252 大卡"
    assert recipe.ingredients == ["西红柿", "鸡蛋", "食用油", "盐"]
    assert recipe.steps[0] == "西红柿洗净切块。"
    assert recipe.notes == ["可以加葱花。"]


def test_load_recipes_walks_dishes_only():
    recipes = load_recipes(FIXTURE_ROOT)

    names = sorted(recipe.name for recipe in recipes)
    assert names == ["水煮牛肉", "西红柿炒鸡蛋"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_parser.py -q
```

Expected: FAIL with `ModuleNotFoundError` or missing parser functions.

- [ ] **Step 3: Implement the parser**

Create `cookqa/parser.py`:

```python
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
    line = line.strip("` ").strip()
    return line


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
        if line.lstrip().startswith(("*", "-", "+")) or re.match(r"^\s*\d+[.)、]\s+", line):
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
    ingredients = _extract_list_items(section_map.get("必备原料和工具", []))
    steps = _extract_list_items(section_map.get("操作", []))
    notes = _extract_list_items(section_map.get("附加内容", []))

    return RecipeDocument(
        recipe_id=relative,
        name=name,
        category=_category_from_path(Path(relative)),
        source_path=relative,
        source_url=f"https://github.com/Anduin2017/HowToCook/blob/master/{relative}",
        description=_first_nonempty(section_map.get("intro", [])),
        difficulty=_extract_metric(raw_text, "预估烹饪难度"),
        calories=_extract_metric(raw_text, "预估卡路里"),
        ingredients=ingredients,
        tools=[],
        steps=steps,
        notes=notes,
        raw_text=raw_text,
    )


def load_recipes(root: Path) -> List[RecipeDocument]:
    dishes_root = root / "dishes"
    if not dishes_root.exists():
        return []
    recipes = [
        parse_recipe_file(path, root)
        for path in sorted(dishes_root.rglob("*.md"))
        if path.is_file()
    ]
    return recipes
```

- [ ] **Step 4: Run parser tests**

Run:

```powershell
python -m pytest tests/test_parser.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit or record changes**

If Git is initialized:

```powershell
git add cookqa/parser.py tests/fixtures tests/test_parser.py
git commit -m "feat: parse HowToCook recipes"
```

If not, record changed files in task notes.

---

### Task 3: Lightweight Recipe Graph

**Files:**
- Create: `cookqa/graph.py`
- Test: `tests/test_graph.py`

**Interfaces:**
- Consumes: `RecipeDocument`
- Produces: `RecipeGraph.build(recipes: list[RecipeDocument]) -> RecipeGraph`
- Produces: `RecipeGraph.match_terms(question: str) -> dict[str, list[str]]`
- Produces: `RecipeGraph.recipe_matches(question: str) -> dict[str, list[str]]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_graph.py`:

```python
from pathlib import Path

from cookqa.graph import RecipeGraph
from cookqa.parser import load_recipes


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "howtocook"


def test_graph_indexes_ingredients_and_categories():
    recipes = load_recipes(FIXTURE_ROOT)
    graph = RecipeGraph.build(recipes)

    matches = graph.recipe_matches("牛肉可以怎么做")

    assert "dishes/meat_dish/水煮牛肉/水煮牛肉.md" in matches
    assert "ingredient:牛肉" in matches["dishes/meat_dish/水煮牛肉/水煮牛肉.md"]


def test_graph_matches_exact_dish_name():
    recipes = load_recipes(FIXTURE_ROOT)
    graph = RecipeGraph.build(recipes)

    matches = graph.recipe_matches("番茄炒蛋怎么做")

    assert "dishes/vegetable_dish/西红柿炒鸡蛋.md" in matches
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_graph.py -q
```

Expected: FAIL with missing `cookqa.graph`.

- [ ] **Step 3: Implement graph matching**

Create `cookqa/graph.py`:

```python
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set

from .models import RecipeDocument


ALIASES = {
    "番茄": "西红柿",
    "西红柿": "西红柿",
    "炒蛋": "鸡蛋",
    "蛋": "鸡蛋",
}


def _normalize_terms(text: str) -> Set[str]:
    terms = {text}
    for alias, canonical in ALIASES.items():
        if alias in text:
            terms.add(canonical)
    return {term for term in terms if term}


@dataclass
class RecipeGraph:
    recipe_names: Dict[str, str]
    relations: Dict[str, List[str]]

    @classmethod
    def build(cls, recipes: Iterable[RecipeDocument]) -> "RecipeGraph":
        recipe_names: Dict[str, str] = {}
        relations: Dict[str, List[str]] = defaultdict(list)
        for recipe in recipes:
            recipe_names[recipe.recipe_id] = recipe.name
            relation_terms = [f"name:{recipe.name}", f"category:{recipe.category}"]
            relation_terms.extend(f"ingredient:{item}" for item in recipe.ingredients)
            relation_terms.extend(f"tool:{item}" for item in recipe.tools)
            for relation in relation_terms:
                relations[relation].append(recipe.recipe_id)
        return cls(recipe_names=recipe_names, relations=dict(relations))

    def match_terms(self, question: str) -> Dict[str, List[str]]:
        matched: Dict[str, List[str]] = {}
        question_terms = _normalize_terms(question)
        for relation, recipe_ids in self.relations.items():
            _, value = relation.split(":", 1)
            candidate_terms = _normalize_terms(value)
            if any(term and term in question for term in candidate_terms | question_terms):
                if value in question or any(term in question for term in candidate_terms):
                    matched[relation] = recipe_ids
        return matched

    def recipe_matches(self, question: str) -> Dict[str, List[str]]:
        by_recipe: Dict[str, List[str]] = defaultdict(list)
        for relation, recipe_ids in self.match_terms(question).items():
            for recipe_id in recipe_ids:
                by_recipe[recipe_id].append(relation)

        for recipe_id, name in self.recipe_names.items():
            if name in question:
                by_recipe[recipe_id].append(f"name:{name}")
            elif "番茄炒蛋" in question and name == "西红柿炒鸡蛋":
                by_recipe[recipe_id].append("name_alias:番茄炒蛋")
        return dict(by_recipe)
```

- [ ] **Step 4: Run graph tests**

Run:

```powershell
python -m pytest tests/test_graph.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit or record changes**

If Git is initialized:

```powershell
git add cookqa/graph.py tests/test_graph.py
git commit -m "feat: add lightweight recipe graph"
```

If not, record changed files.

---

### Task 4: FAISS Index Store With Injectable Embeddings

**Files:**
- Create: `cookqa/index_store.py`
- Test: `tests/test_index_store.py`

**Interfaces:**
- Consumes: `RecipeDocument`, `RecipeChunk`
- Produces: `build_recipe_chunks(recipes: list[RecipeDocument]) -> list[RecipeChunk]`
- Produces: `build_step_chunks(recipes: list[RecipeDocument]) -> list[RecipeChunk]`
- Produces: `FaissIndexStore.build(chunks, embed_texts, index_path, payload_path) -> None`
- Produces: `FaissIndexStore.load(index_path, payload_path) -> FaissIndexStore`
- Produces: `FaissIndexStore.search(query, embed_query, top_k) -> list[tuple[RecipeChunk, float]]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_index_store.py`:

```python
from pathlib import Path

from cookqa.index_store import FaissIndexStore, build_recipe_chunks, build_step_chunks
from cookqa.parser import load_recipes


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "howtocook"


def fake_embed_texts(texts):
    vectors = []
    for text in texts:
        vectors.append([
            1.0 if "牛肉" in text else 0.0,
            1.0 if "西红柿" in text else 0.0,
            1.0 if "鸡蛋" in text else 0.0,
        ])
    return vectors


def fake_embed_query(text):
    return fake_embed_texts([text])[0]


def test_build_recipe_and_step_chunks():
    recipes = load_recipes(FIXTURE_ROOT)

    recipe_chunks = build_recipe_chunks(recipes)
    step_chunks = build_step_chunks(recipes)

    assert {chunk.kind for chunk in recipe_chunks} == {"recipe"}
    assert {chunk.kind for chunk in step_chunks} == {"step"}
    assert any(chunk.name == "水煮牛肉" for chunk in recipe_chunks)
    assert any("红汤" in chunk.text for chunk in step_chunks)


def test_faiss_store_searches_payloads(tmp_path):
    recipes = load_recipes(FIXTURE_ROOT)
    chunks = build_recipe_chunks(recipes)
    index_path = tmp_path / "recipes.faiss"
    payload_path = tmp_path / "recipes.payload.json"

    FaissIndexStore.build(chunks, fake_embed_texts, index_path, payload_path)
    store = FaissIndexStore.load(index_path, payload_path)
    results = store.search("牛肉可以怎么做", fake_embed_query, top_k=1)

    assert results[0][0].name == "水煮牛肉"
    assert results[0][1] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_index_store.py -q
```

Expected: FAIL with missing index store.

- [ ] **Step 3: Implement FAISS store**

Create `cookqa/index_store.py`:

```python
import json
from pathlib import Path
from typing import Callable, Iterable, List, Sequence, Tuple

import faiss
import numpy as np

from .models import RecipeChunk, RecipeDocument


EmbedTexts = Callable[[Sequence[str]], Sequence[Sequence[float]]]
EmbedQuery = Callable[[str], Sequence[float]]


def _as_matrix(vectors: Sequence[Sequence[float]]) -> np.ndarray:
    matrix = np.asarray(vectors, dtype="float32")
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("embedding matrix must be non-empty and two-dimensional")
    faiss.normalize_L2(matrix)
    return matrix


def build_recipe_chunks(recipes: Iterable[RecipeDocument]) -> List[RecipeChunk]:
    chunks: List[RecipeChunk] = []
    for recipe in recipes:
        chunks.append(
            RecipeChunk(
                chunk_id=f"{recipe.recipe_id}#recipe",
                recipe_id=recipe.recipe_id,
                name=recipe.name,
                source_path=recipe.source_path,
                text=recipe.search_text(),
                kind="recipe",
                ordinal=0,
            )
        )
    return chunks


def build_step_chunks(recipes: Iterable[RecipeDocument]) -> List[RecipeChunk]:
    chunks: List[RecipeChunk] = []
    for recipe in recipes:
        for index, step in enumerate(recipe.steps, start=1):
            chunks.append(
                RecipeChunk(
                    chunk_id=f"{recipe.recipe_id}#step-{index}",
                    recipe_id=recipe.recipe_id,
                    name=recipe.name,
                    source_path=recipe.source_path,
                    text=step,
                    kind="step",
                    ordinal=index,
                )
            )
    return chunks


class FaissIndexStore:
    def __init__(self, index: faiss.Index, payloads: List[RecipeChunk]):
        self.index = index
        self.payloads = payloads

    @classmethod
    def build(
        cls,
        chunks: Sequence[RecipeChunk],
        embed_texts: EmbedTexts,
        index_path: Path,
        payload_path: Path,
    ) -> None:
        if not chunks:
            raise ValueError("cannot build FAISS index without chunks")
        vectors = _as_matrix(embed_texts([chunk.text for chunk in chunks]))
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(index_path))
        payload_path.write_text(
            json.dumps([chunk.model_dump() for chunk in chunks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, index_path: Path, payload_path: Path) -> "FaissIndexStore":
        if not index_path.exists() or not payload_path.exists():
            raise FileNotFoundError("FAISS index or payload file is missing")
        index = faiss.read_index(str(index_path))
        raw_payloads = json.loads(payload_path.read_text(encoding="utf-8"))
        return cls(index=index, payloads=[RecipeChunk(**item) for item in raw_payloads])

    def search(
        self,
        query: str,
        embed_query: EmbedQuery,
        top_k: int,
    ) -> List[Tuple[RecipeChunk, float]]:
        query_matrix = _as_matrix([embed_query(query)])
        scores, indexes = self.index.search(query_matrix, top_k)
        results: List[Tuple[RecipeChunk, float]] = []
        for score, index in zip(scores[0].tolist(), indexes[0].tolist()):
            if index < 0:
                continue
            results.append((self.payloads[index], float(score)))
        return results
```

- [ ] **Step 4: Run index tests**

Run:

```powershell
python -m pytest tests/test_index_store.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit or record changes**

If Git is initialized:

```powershell
git add cookqa/index_store.py tests/test_index_store.py
git commit -m "feat: add FAISS index store"
```

If not, record changed files.

---

### Task 5: Ollama Client And Answer Generator

**Files:**
- Create: `cookqa/ollama_client.py`
- Create: `cookqa/generation.py`
- Test: `tests/test_generation.py`

**Interfaces:**
- Produces: `OllamaClient.embed_texts(texts: Sequence[str]) -> list[list[float]]`
- Produces: `OllamaClient.chat(prompt: str) -> str`
- Produces: `AnswerGenerator.generate(question: str, mode: QueryMode, recommendations: list[Recommendation]) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_generation.py`:

```python
from cookqa.generation import AnswerGenerator
from cookqa.models import Recommendation


class FailingChatClient:
    def chat(self, prompt: str) -> str:
        raise RuntimeError("ollama unavailable")


class StaticChatClient:
    def chat(self, prompt: str) -> str:
        assert "不要编造" in prompt
        return "可以做水煮牛肉，先腌制牛肉，再煮红汤。"


def recommendation():
    return Recommendation(
        recipe_id="dishes/meat_dish/水煮牛肉/水煮牛肉.md",
        name="水煮牛肉",
        score=0.91,
        match_reason="命中食材：牛肉",
        ingredients=["牛肉", "豆芽"],
        summary_steps=["腌制牛肉", "煮红汤"],
        source_path="dishes/meat_dish/水煮牛肉/水煮牛肉.md",
        graph_matches=["ingredient:牛肉"],
    )


def test_generator_uses_chat_client_when_available():
    answer = AnswerGenerator(StaticChatClient()).generate(
        "牛肉可以怎么做",
        "ingredient_exploration",
        [recommendation()],
    )

    assert "水煮牛肉" in answer


def test_generator_falls_back_when_chat_client_fails():
    answer = AnswerGenerator(FailingChatClient()).generate(
        "牛肉可以怎么做",
        "ingredient_exploration",
        [recommendation()],
    )

    assert "水煮牛肉" in answer
    assert "当前未连接到可用的生成模型" in answer
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_generation.py -q
```

Expected: FAIL with missing generation module.

- [ ] **Step 3: Implement Ollama client and generator**

Create `cookqa/ollama_client.py`:

```python
from typing import Sequence

import httpx


class OllamaClient:
    def __init__(self, base_url: str, embedding_model: str, chat_model: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.embedding_model = embedding_model
        self.chat_model = chat_model
        self.timeout = timeout

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        with httpx.Client(timeout=self.timeout) as client:
            for text in texts:
                response = client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.embedding_model, "prompt": text},
                )
                response.raise_for_status()
                vectors.append(response.json()["embedding"])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def chat(self, prompt: str) -> str:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/generate",
                json={"model": self.chat_model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
```

Create `cookqa/generation.py`:

```python
from typing import Protocol

from .models import QueryMode, Recommendation


class ChatClient(Protocol):
    def chat(self, prompt: str) -> str:
        ...


class AnswerGenerator:
    def __init__(self, chat_client: ChatClient | None):
        self.chat_client = chat_client

    def generate(
        self,
        question: str,
        mode: QueryMode,
        recommendations: list[Recommendation],
    ) -> str:
        if not recommendations:
            return "没有在 HowToCook 菜谱库中找到足够相关的菜谱。"

        prompt = self._build_prompt(question, mode, recommendations)
        if self.chat_client is not None:
            try:
                answer = self.chat_client.chat(prompt)
                if answer:
                    return answer
            except Exception:
                pass
        return self._fallback_answer(mode, recommendations)

    def _build_prompt(
        self,
        question: str,
        mode: QueryMode,
        recommendations: list[Recommendation],
    ) -> str:
        recipe_lines = []
        for item in recommendations:
            recipe_lines.append(
                "\n".join(
                    [
                        f"菜谱：{item.name}",
                        f"匹配原因：{item.match_reason}",
                        f"原料：{'、'.join(item.ingredients)}",
                        f"步骤摘要：{'；'.join(item.summary_steps)}",
                        f"来源：{item.source_path}",
                    ]
                )
            )
        context = "\n\n".join(recipe_lines)
        return (
            "你是中文做饭助手食神。只能根据给定菜谱回答，不要编造不存在的菜谱、食材、步骤、热量或难度。\n"
            f"用户问题：{question}\n"
            f"检索模式：{mode}\n"
            f"候选菜谱：\n{context}\n"
            "请先给推荐结论，再给最相关菜谱的简明做法。"
        )

    def _fallback_answer(self, mode: QueryMode, recommendations: list[Recommendation]) -> str:
        names = "、".join(item.name for item in recommendations[:5])
        first = recommendations[0]
        steps = "；".join(first.summary_steps)
        if mode == "missing_or_fictional":
            prefix = "没有找到精确菜谱，下面是相近的 HowToCook 菜谱。"
        else:
            prefix = "当前未连接到可用的生成模型，先返回基于检索结果的答案。"
        return f"{prefix} 推荐：{names}。最相关的是 {first.name}，主要步骤：{steps}。"
```

- [ ] **Step 4: Run generation tests**

Run:

```powershell
python -m pytest tests/test_generation.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit or record changes**

If Git is initialized:

```powershell
git add cookqa/ollama_client.py cookqa/generation.py tests/test_generation.py
git commit -m "feat: add grounded answer generation"
```

If not, record changed files.

---

### Task 6: Retrieval Orchestration

**Files:**
- Create: `cookqa/retrieval.py`
- Test: `tests/test_retrieval.py`

**Interfaces:**
- Consumes: `RecipeDocument`, `RecipeGraph`, optional `FaissIndexStore`
- Produces: `detect_mode(question: str, graph_matches: dict[str, list[str]]) -> QueryMode`
- Produces: `RecipeRetriever.search(question: str, top_k: int) -> tuple[QueryMode, list[Recommendation]]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retrieval.py`:

```python
from pathlib import Path

from cookqa.graph import RecipeGraph
from cookqa.parser import load_recipes
from cookqa.retrieval import RecipeRetriever


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "howtocook"


def build_retriever():
    recipes = load_recipes(FIXTURE_ROOT)
    graph = RecipeGraph.build(recipes)
    return RecipeRetriever(recipes=recipes, graph=graph, recipe_index=None, step_index=None, embed_query=None)


def test_ingredient_question_returns_multiple_recommendations():
    mode, recommendations = build_retriever().search("牛肉可以怎么做", top_k=5)

    assert mode == "ingredient_exploration"
    assert recommendations[0].name == "水煮牛肉"
    assert "牛肉" in recommendations[0].match_reason


def test_alias_dish_question_finds_tomato_egg():
    mode, recommendations = build_retriever().search("番茄炒蛋怎么做", top_k=3)

    assert mode == "dish_lookup"
    assert recommendations[0].name == "西红柿炒鸡蛋"


def test_missing_question_marks_no_exact_match():
    mode, recommendations = build_retriever().search("黯然销魂饭怎么做", top_k=3)

    assert mode == "missing_or_fictional"
    assert recommendations == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_retrieval.py -q
```

Expected: FAIL with missing retrieval module.

- [ ] **Step 3: Implement retrieval**

Create `cookqa/retrieval.py`:

```python
from collections import defaultdict
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .graph import RecipeGraph
from .index_store import FaissIndexStore
from .models import QueryMode, Recommendation, RecipeDocument


EmbedQuery = Callable[[str], list[float]]


def detect_mode(question: str, graph_matches: Dict[str, List[str]]) -> QueryMode:
    if not graph_matches and any(term in question for term in ["黯然销魂饭"]):
        return "missing_or_fictional"
    if any(relation.startswith(("name:", "name_alias:")) for matches in graph_matches.values() for relation in matches):
        return "dish_lookup"
    if any(relation.startswith("ingredient:") for matches in graph_matches.values() for relation in matches):
        return "ingredient_exploration"
    if "怎么做" in question:
        return "dish_lookup" if graph_matches else "missing_or_fictional"
    return "general"


class RecipeRetriever:
    def __init__(
        self,
        recipes: Iterable[RecipeDocument],
        graph: RecipeGraph,
        recipe_index: Optional[FaissIndexStore],
        step_index: Optional[FaissIndexStore],
        embed_query: Optional[EmbedQuery],
    ):
        self.recipes = {recipe.recipe_id: recipe for recipe in recipes}
        self.graph = graph
        self.recipe_index = recipe_index
        self.step_index = step_index
        self.embed_query = embed_query

    def search(self, question: str, top_k: int) -> Tuple[QueryMode, List[Recommendation]]:
        graph_matches = self.graph.recipe_matches(question)
        mode = detect_mode(question, graph_matches)
        scores: Dict[str, float] = defaultdict(float)
        reasons: Dict[str, List[str]] = defaultdict(list)

        for recipe_id, relations in graph_matches.items():
            scores[recipe_id] += 0.65 + 0.05 * min(len(relations), 4)
            reasons[recipe_id].extend(relations)

        if self.recipe_index is not None and self.embed_query is not None:
            for chunk, score in self.recipe_index.search(question, self.embed_query, top_k=top_k):
                scores[chunk.recipe_id] += score * 0.35
                reasons[chunk.recipe_id].append("vector:recipe")

        if mode == "missing_or_fictional" and not scores:
            return mode, []

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
        recommendations = [
            self._recommendation(recipe_id, score, reasons[recipe_id])
            for recipe_id, score in ranked
            if recipe_id in self.recipes
        ]
        return mode, recommendations

    def _recommendation(self, recipe_id: str, score: float, reasons: List[str]) -> Recommendation:
        recipe = self.recipes[recipe_id]
        readable_reasons = []
        for reason in reasons:
            if reason.startswith("ingredient:"):
                readable_reasons.append(f"命中食材：{reason.split(':', 1)[1]}")
            elif reason.startswith("category:"):
                readable_reasons.append(f"命中类别：{reason.split(':', 1)[1]}")
            elif reason.startswith(("name:", "name_alias:")):
                readable_reasons.append("命中菜名")
            elif reason == "vector:recipe":
                readable_reasons.append("语义相似度高")
        match_reason = "；".join(dict.fromkeys(readable_reasons)) or "综合相关度较高"
        return Recommendation(
            recipe_id=recipe.recipe_id,
            name=recipe.name,
            score=round(float(score), 4),
            match_reason=match_reason,
            ingredients=recipe.ingredients,
            summary_steps=recipe.summary_steps(),
            source_path=recipe.source_path,
            source_url=recipe.source_url,
            graph_matches=reasons,
        )
```

- [ ] **Step 4: Run retrieval tests**

Run:

```powershell
python -m pytest tests/test_retrieval.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit or record changes**

If Git is initialized:

```powershell
git add cookqa/retrieval.py tests/test_retrieval.py
git commit -m "feat: rank recipe recommendations"
```

If not, record changed files.

---

### Task 7: CookQA Service And Index Rebuild

**Files:**
- Create: `cookqa/service.py`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: settings, parser, graph, FAISS store, retriever, generator
- Produces: `CookQAService.from_settings(settings: CookQASettings) -> CookQAService`
- Produces: `CookQAService.rebuild_indexes() -> dict[str, int]`
- Produces: `CookQAService.chat(question: str, top_k: int, include_steps: bool) -> ChatResult`
- Produces: `CookQAService.search(question: str, top_k: int) -> tuple[QueryMode, list[Recommendation]]`
- Produces: `CookQAService.get_recipe(recipe_id: str) -> RecipeDocument`

- [ ] **Step 1: Write the failing service tests**

Create `tests/test_service.py`:

```python
from pathlib import Path

import pytest

from cookqa.config import CookQASettings
from cookqa.service import CookQAService


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "howtocook"


def settings_for(tmp_path):
    return CookQASettings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        howtocook_path=FIXTURE_ROOT,
        ollama_base_url="http://127.0.0.1:11434",
        embedding_model="bge-m3",
        chat_model="gpt-oss:120b-cloud",
        top_k=5,
        min_score=0.15,
        enable_rebuild_api=True,
    )


def test_service_rebuild_writes_metadata_without_live_ollama(tmp_path):
    service = CookQAService.from_settings(settings_for(tmp_path), ollama_client=None)

    result = service.rebuild_metadata()

    assert result["recipes"] == 2
    assert (tmp_path / "data" / "parsed" / "recipes.json").exists()
    assert (tmp_path / "data" / "graph" / "relations.json").exists()


def test_service_chat_returns_answer_and_sources(tmp_path):
    service = CookQAService.from_settings(settings_for(tmp_path), ollama_client=None)
    service.rebuild_metadata()

    result = service.chat("番茄炒蛋怎么做", top_k=3, include_steps=True)

    assert result.mode == "dish_lookup"
    assert result.recommendations[0].name == "西红柿炒鸡蛋"
    assert result.sources[0].name == "西红柿炒鸡蛋"


def test_get_recipe_raises_key_error_for_unknown_recipe(tmp_path):
    service = CookQAService.from_settings(settings_for(tmp_path), ollama_client=None)
    service.rebuild_metadata()

    with pytest.raises(KeyError):
        service.get_recipe("missing.md")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_service.py -q
```

Expected: FAIL with missing service module.

- [ ] **Step 3: Implement service facade**

Create `cookqa/service.py`:

```python
import json
from pathlib import Path
from typing import Optional

from .config import CookQASettings
from .generation import AnswerGenerator
from .graph import RecipeGraph
from .index_store import FaissIndexStore, build_recipe_chunks, build_step_chunks
from .models import ChatResult, RecipeDocument, Recommendation, SourceRef
from .ollama_client import OllamaClient
from .parser import load_recipes
from .retrieval import RecipeRetriever


class CookQAService:
    def __init__(
        self,
        settings: CookQASettings,
        recipes: list[RecipeDocument],
        graph: RecipeGraph,
        recipe_index: Optional[FaissIndexStore],
        step_index: Optional[FaissIndexStore],
        ollama_client: Optional[OllamaClient],
    ):
        self.settings = settings
        self.recipes = {recipe.recipe_id: recipe for recipe in recipes}
        self.graph = graph
        self.recipe_index = recipe_index
        self.step_index = step_index
        self.ollama_client = ollama_client

    @classmethod
    def from_settings(
        cls,
        settings: CookQASettings,
        ollama_client: Optional[OllamaClient] = None,
    ) -> "CookQAService":
        if ollama_client is None:
            ollama_client = OllamaClient(
                settings.ollama_base_url,
                settings.embedding_model,
                settings.chat_model,
            )
        recipes = cls._load_recipe_metadata(settings.parsed_recipes_path)
        graph = RecipeGraph.build(recipes)
        recipe_index = cls._load_index(settings.recipe_index_path, settings.recipe_payload_path)
        step_index = cls._load_index(settings.step_index_path, settings.step_payload_path)
        return cls(settings, recipes, graph, recipe_index, step_index, ollama_client)

    @staticmethod
    def _load_recipe_metadata(path: Path) -> list[RecipeDocument]:
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [RecipeDocument(**item) for item in raw]

    @staticmethod
    def _load_index(index_path: Path, payload_path: Path) -> Optional[FaissIndexStore]:
        try:
            return FaissIndexStore.load(index_path, payload_path)
        except FileNotFoundError:
            return None

    def rebuild_metadata(self) -> dict[str, int]:
        recipes = load_recipes(self.settings.howtocook_path)
        self.settings.parsed_dir.mkdir(parents=True, exist_ok=True)
        self.settings.graph_dir.mkdir(parents=True, exist_ok=True)
        self.settings.parsed_recipes_path.write_text(
            json.dumps([recipe.model_dump() for recipe in recipes], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        graph = RecipeGraph.build(recipes)
        self.settings.graph_path.write_text(
            json.dumps(graph.relations, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.recipes = {recipe.recipe_id: recipe for recipe in recipes}
        self.graph = graph
        return {"recipes": len(recipes), "relations": len(graph.relations)}

    def rebuild_indexes(self) -> dict[str, int]:
        self.rebuild_metadata()
        if self.ollama_client is None:
            raise RuntimeError("Ollama client is required to rebuild FAISS indexes")
        recipes = list(self.recipes.values())
        recipe_chunks = build_recipe_chunks(recipes)
        step_chunks = build_step_chunks(recipes)
        FaissIndexStore.build(
            recipe_chunks,
            self.ollama_client.embed_texts,
            self.settings.recipe_index_path,
            self.settings.recipe_payload_path,
        )
        FaissIndexStore.build(
            step_chunks,
            self.ollama_client.embed_texts,
            self.settings.step_index_path,
            self.settings.step_payload_path,
        )
        self.recipe_index = FaissIndexStore.load(self.settings.recipe_index_path, self.settings.recipe_payload_path)
        self.step_index = FaissIndexStore.load(self.settings.step_index_path, self.settings.step_payload_path)
        return {"recipes": len(recipes), "recipe_chunks": len(recipe_chunks), "step_chunks": len(step_chunks)}

    def search(self, question: str, top_k: int):
        retriever = RecipeRetriever(
            recipes=self.recipes.values(),
            graph=self.graph,
            recipe_index=self.recipe_index,
            step_index=self.step_index,
            embed_query=self.ollama_client.embed_query if self.ollama_client else None,
        )
        return retriever.search(question, top_k)

    def chat(self, question: str, top_k: int, include_steps: bool) -> ChatResult:
        mode, recommendations = self.search(question, top_k)
        if not include_steps:
            recommendations = [
                item.model_copy(update={"summary_steps": []})
                for item in recommendations
            ]
        answer = AnswerGenerator(self.ollama_client).generate(question, mode, recommendations)
        sources = [
            SourceRef(
                recipe_id=item.recipe_id,
                name=item.name,
                source_path=item.source_path,
                source_url=item.source_url,
            )
            for item in recommendations
        ]
        return ChatResult(
            answer=answer,
            mode=mode,
            recommendations=recommendations,
            sources=sources,
            metadata={"top_k": top_k},
        )

    def get_recipe(self, recipe_id: str) -> RecipeDocument:
        recipe = self.recipes.get(recipe_id)
        if recipe is None:
            raise KeyError(recipe_id)
        return recipe
```

- [ ] **Step 4: Run service tests**

Run:

```powershell
python -m pytest tests/test_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit or record changes**

If Git is initialized:

```powershell
git add cookqa/service.py tests/test_service.py
git commit -m "feat: orchestrate CookQA service"
```

If not, record changed files.

---

### Task 8: FastAPI API Replacement

**Files:**
- Replace: `api/schemas.py`
- Replace: `api/app.py`
- Replace: `tests/test_api.py`

**Interfaces:**
- Consumes: `CookQAService`
- Produces: `GET /health`
- Produces: `POST /api/v1/chat`
- Produces: `GET /api/v1/recipes/search`
- Produces: `GET /api/v1/recipes/{recipe_id:path}`
- Produces: `POST /api/v1/index/rebuild`

- [ ] **Step 1: Write the failing API tests**

Replace `tests/test_api.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from cookqa.config import CookQASettings


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "howtocook"


def test_health_endpoint(tmp_path):
    client = TestClient(create_app(settings_for(tmp_path), ollama_client=None))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["service"] == "CookQA"


def test_chat_endpoint_returns_recommendations(tmp_path):
    settings = settings_for(tmp_path)
    app = create_app(settings, ollama_client=None)
    client = TestClient(app)
    client.post("/api/v1/index/rebuild", params={"vectors": "false"})

    response = client.post("/api/v1/chat", json={"question": "番茄炒蛋怎么做", "top_k": 3})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "dish_lookup"
    assert body["recommendations"][0]["name"] == "西红柿炒鸡蛋"


def test_search_endpoint_returns_ranked_items(tmp_path):
    settings = settings_for(tmp_path)
    app = create_app(settings, ollama_client=None)
    client = TestClient(app)
    client.post("/api/v1/index/rebuild", params={"vectors": "false"})

    response = client.get("/api/v1/recipes/search", params={"q": "牛肉可以怎么做", "top_k": 5})

    assert response.status_code == 200
    assert response.json()["recommendations"][0]["name"] == "水煮牛肉"


def settings_for(tmp_path):
    return CookQASettings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        howtocook_path=FIXTURE_ROOT,
        ollama_base_url="http://127.0.0.1:11434",
        embedding_model="bge-m3",
        chat_model="gpt-oss:120b-cloud",
        top_k=5,
        min_score=0.15,
        enable_rebuild_api=True,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_api.py -q
```

Expected: FAIL because the old API exposes BaseQA endpoints.

- [ ] **Step 3: Replace API schemas**

Replace `api/schemas.py`:

```python
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator

from cookqa.models import QueryMode, Recommendation, SourceRef


class ChatRequest(BaseModel):
    question: str = Field(..., examples=["牛肉可以怎么做"])
    top_k: int = Field(5, ge=1, le=20)
    include_steps: bool = True

    @field_validator("question")
    @classmethod
    def question_must_not_be_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question cannot be empty")
        return stripped


class ChatResponse(BaseModel):
    answer: str
    mode: QueryMode
    recommendations: List[Recommendation]
    sources: List[SourceRef]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    mode: QueryMode
    recommendations: List[Recommendation]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class RebuildResponse(BaseModel):
    status: str
    result: Dict[str, int]
```

- [ ] **Step 4: Replace FastAPI app**

Replace `api/app.py`:

```python
from pathlib import Path
import sys

from fastapi import FastAPI, HTTPException, Query

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cookqa import __version__
from cookqa.config import CookQASettings
from cookqa.ollama_client import OllamaClient
from cookqa.service import CookQAService

from .schemas import ChatRequest, ChatResponse, HealthResponse, RebuildResponse, SearchResponse


def create_app(
    settings: CookQASettings | None = None,
    ollama_client: OllamaClient | None = None,
) -> FastAPI:
    settings = settings or CookQASettings.from_env()
    service = CookQAService.from_settings(settings, ollama_client=ollama_client)

    app = FastAPI(
        title="CookQA API",
        description="食神 CookQA 食谱 GraphRAG API",
        version=__version__,
    )
    app.state.cookqa_service = service
    app.state.cookqa_settings = settings

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="CookQA", version=__version__)

    @app.post("/api/v1/chat", response_model=ChatResponse, tags=["cookqa"])
    def chat(request: ChatRequest) -> ChatResponse:
        result = app.state.cookqa_service.chat(
            request.question,
            top_k=request.top_k,
            include_steps=request.include_steps,
        )
        return ChatResponse(**result.model_dump())

    @app.get("/api/v1/recipes/search", response_model=SearchResponse, tags=["cookqa"])
    def search(q: str = Query(..., min_length=1), top_k: int = Query(5, ge=1, le=20)) -> SearchResponse:
        mode, recommendations = app.state.cookqa_service.search(q.strip(), top_k=top_k)
        return SearchResponse(mode=mode, recommendations=recommendations)

    @app.get("/api/v1/recipes/{recipe_id:path}", tags=["cookqa"])
    def recipe_detail(recipe_id: str):
        try:
            return app.state.cookqa_service.get_recipe(recipe_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="recipe not found") from exc

    @app.post("/api/v1/index/rebuild", response_model=RebuildResponse, tags=["cookqa"])
    def rebuild(vectors: bool = Query(False)) -> RebuildResponse:
        if not app.state.cookqa_settings.enable_rebuild_api:
            raise HTTPException(status_code=403, detail="index rebuild API is disabled")
        if vectors:
            result = app.state.cookqa_service.rebuild_indexes()
        else:
            result = app.state.cookqa_service.rebuild_metadata()
        return RebuildResponse(status="ok", result=result)

    return app


app = create_app()
```

- [ ] **Step 5: Run API tests**

Run:

```powershell
python -m pytest tests/test_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit or record changes**

If Git is initialized:

```powershell
git add api/app.py api/schemas.py tests/test_api.py
git commit -m "feat: expose CookQA FastAPI endpoints"
```

If not, record changed files.

---

### Task 9: CLI, Documentation, And Docker

**Files:**
- Replace: `main.py`
- Replace: `README.md`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`
- Test: `tests/test_cli_import.py`

**Interfaces:**
- Consumes: `CookQAService`
- Produces: `python main.py chat "问题"`
- Produces: `python main.py rebuild --metadata-only`
- Produces: Docker image running `uvicorn api.app:app --host 0.0.0.0 --port 8000`

- [ ] **Step 1: Write import test**

Create `tests/test_cli_import.py`:

```python
import main


def test_main_module_imports():
    assert callable(main.main)
```

- [ ] **Step 2: Replace CLI**

Replace `main.py`:

```python
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cookqa.config import CookQASettings
from cookqa.service import CookQAService


def main() -> None:
    parser = argparse.ArgumentParser(description="CookQA 食神食谱问答")
    subparsers = parser.add_subparsers(dest="command", required=True)

    chat_parser = subparsers.add_parser("chat", help="Ask a cooking question")
    chat_parser.add_argument("question")
    chat_parser.add_argument("--top-k", type=int, default=5)
    chat_parser.add_argument("--no-steps", action="store_true")

    rebuild_parser = subparsers.add_parser("rebuild", help="Rebuild metadata or vector indexes")
    rebuild_parser.add_argument("--metadata-only", action="store_true")

    args = parser.parse_args()
    service = CookQAService.from_settings(CookQASettings.from_env())

    if args.command == "chat":
        result = service.chat(args.question, top_k=args.top_k, include_steps=not args.no_steps)
        print(result.model_dump_json(indent=2))
        return

    if args.command == "rebuild":
        result = service.rebuild_metadata() if args.metadata_only else service.rebuild_indexes()
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Add Docker files**

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Create `docker-compose.yml`:

```yaml
services:
  cookqa:
    build: .
    container_name: cookqa-api
    ports:
      - "8000:8000"
    environment:
      OLLAMA_BASE_URL: ${OLLAMA_BASE_URL:-http://host.docker.internal:11434}
      OLLAMA_EMBEDDING_MODEL: ${OLLAMA_EMBEDDING_MODEL:-bge-m3}
      OLLAMA_CHAT_MODEL: ${OLLAMA_CHAT_MODEL:-gpt-oss:120b-cloud}
      COOKQA_DATA_DIR: /app/data
      HOWTOCOOK_PATH: /app/data/HowToCook
      COOKQA_ENABLE_REBUILD_API: ${COOKQA_ENABLE_REBUILD_API:-true}
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

Create `.dockerignore`:

```text
__pycache__/
*.pyc
.pytest_cache/
.git/
logs/
data/
*.faiss
*.payload.json
```

- [ ] **Step 4: Replace README**

Replace `README.md` with:

```markdown
# CookQA 食神

CookQA is a FastAPI-first Chinese recipe GraphRAG service based on HowToCook,
FAISS, and Ollama.

## Features

- Parse HowToCook Markdown recipes.
- Build lightweight recipe graph relations.
- Build FAISS recipe and step indexes with Ollama `bge-m3`.
- Answer Chinese cooking questions with Ollama `gpt-oss:120b-cloud`.
- Return recommendation lists, match reasons, sources, and grounded answers.
- Run locally or with Docker.

## Local Setup

```powershell
pip install -r requirements.txt
$env:HOWTOCOOK_PATH="D:\path\to\HowToCook"
$env:OLLAMA_BASE_URL="http://127.0.0.1:11434"
python main.py rebuild
uvicorn api.app:app --host 127.0.0.1 --port 8000
```

## API Examples

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/chat `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"牛肉可以怎么做\",\"top_k\":5}"
```

## Docker

```powershell
docker compose up --build
```

The Docker image runs CookQA only. Ollama stays external and is configured by
`OLLAMA_BASE_URL`.
```

- [ ] **Step 5: Run CLI import test and full unit suite**

Run:

```powershell
python -m pytest tests -q
```

Expected: PASS.

- [ ] **Step 6: Docker build sanity check**

Run:

```powershell
docker build -t cookqa:dev .
```

Expected: image builds successfully.

- [ ] **Step 7: Commit or record changes**

If Git is initialized:

```powershell
git add main.py README.md Dockerfile docker-compose.yml .dockerignore tests/test_cli_import.py
git commit -m "feat: add CookQA CLI and Docker deployment"
```

If not, record changed files.

---

### Task 10: End-To-End Verification

**Files:**
- Modify only if verification exposes a defect in earlier tasks.

**Interfaces:**
- Consumes: all previous tasks
- Produces: verified local test suite and optional live Ollama indexing path

- [ ] **Step 1: Run the full unit suite**

Run:

```powershell
cd D:\WorkSpace\Code\Project100\CookQA
python -m pytest tests -q
```

Expected: PASS.

- [ ] **Step 2: Run metadata rebuild against fixture path**

Run:

```powershell
$env:HOWTOCOOK_PATH="D:\WorkSpace\Code\Project100\CookQA\tests\fixtures\howtocook"
$env:COOKQA_DATA_DIR="D:\WorkSpace\Code\Project100\CookQA\.tmp-data"
python main.py rebuild --metadata-only
```

Expected JSON:

```json
{
  "recipes": 2,
  "relations": 11
}
```

The exact relation count may be higher if parser extraction includes additional normalized aliases. If it differs, inspect `data/graph/relations.json` and update the test only when the extra relations are correct and deterministic.

- [ ] **Step 3: Run API smoke test**

Run:

```powershell
$env:HOWTOCOOK_PATH="D:\WorkSpace\Code\Project100\CookQA\tests\fixtures\howtocook"
$env:COOKQA_DATA_DIR="D:\WorkSpace\Code\Project100\CookQA\.tmp-data"
uvicorn api.app:app --host 127.0.0.1 --port 8000
```

In a second shell:

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/chat -H "Content-Type: application/json" -d "{\"question\":\"番茄炒蛋怎么做\",\"top_k\":3}"
```

Expected: response contains `"name":"西红柿炒鸡蛋"` and `"mode":"dish_lookup"`.

- [ ] **Step 4: Optional live Ollama verification**

Run only when Ollama is running and both models are available:

```powershell
$env:HOWTOCOOK_PATH="D:\path\to\HowToCook"
$env:COOKQA_DATA_DIR="D:\WorkSpace\Code\Project100\CookQA\data"
$env:OLLAMA_BASE_URL="http://127.0.0.1:11434"
python main.py rebuild
python main.py chat "牛肉可以怎么做"
python main.py chat "番茄炒蛋怎么做"
python main.py chat "黯然销魂饭怎么做"
```

Expected:

- 牛肉 query returns multiple beef-related recommendations.
- 番茄炒蛋 query returns 西红柿炒鸡蛋 as the top recommendation.
- 黯然销魂饭 query does not claim an exact HowToCook source unless one exists.

- [ ] **Step 5: Docker verification**

Run:

```powershell
docker compose up --build
```

Expected: CookQA starts on `http://127.0.0.1:8000`. `/health` returns service `CookQA`.

- [ ] **Step 6: Final review**

Check:

```powershell
rg -n "BaseQA|customer|FAQ|订单|售后" README.md api cookqa tests
rg -n "TO[D]O|TB[D]|placehold[e]r" README.md api cookqa tests docs/superpowers/plans/2026-07-06-cookqa-implementation.md
```

Expected: no stale BaseQA product references in active code/docs, no incomplete-work markers in active implementation or this plan.
