from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from cookqa.models import QueryPlan, RankedCandidate, Recipe


_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+")


def tokenize(text: str) -> list[str]:
    chunks = _TOKEN_RE.findall(text.casefold())
    tokens: list[str] = []
    for chunk in chunks:
        if re.fullmatch(r"[\u4e00-\u9fff]+", chunk):
            tokens.append(chunk)
            tokens.extend(chunk[index : index + 2] for index in range(max(0, len(chunk) - 1)))
            tokens.extend(chunk)
        else:
            tokens.append(chunk)
    return [token for token in tokens if token]


def recipe_document(recipe: Recipe) -> str:
    weighted = [recipe.name] * 5
    weighted.extend(recipe.aliases * 4)
    weighted.extend(ingredient.name for ingredient in recipe.ingredients for _ in range(3))
    weighted.extend(recipe.categories * 2)
    weighted.extend(recipe.methods * 2)
    weighted.extend(recipe.tools * 2)
    weighted.extend(recipe.tags * 2)
    if recipe.summary:
        weighted.append(recipe.summary)
    weighted.extend(recipe.steps)
    return " ".join(weighted)


class BM25Retriever:
    name = "bm25"

    def __init__(self, recipe_ids: list[str], documents: list[list[str]], k1: float = 1.5, b: float = 0.75):
        if len(recipe_ids) != len(documents):
            raise ValueError("recipe_ids 与 documents 数量不一致")
        self.recipe_ids = recipe_ids
        self.documents = documents
        self.k1 = k1
        self.b = b
        self._lengths = [len(document) for document in documents]
        self._average_length = sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        self._frequencies = [Counter(document) for document in documents]
        document_frequency: Counter[str] = Counter()
        for document in documents:
            document_frequency.update(set(document))
        count = len(documents)
        self._idf = {
            token: math.log(1 + (count - frequency + 0.5) / (frequency + 0.5))
            for token, frequency in document_frequency.items()
        }

    @classmethod
    def build(cls, recipes: list[Recipe]) -> "BM25Retriever":
        return cls(
            recipe_ids=[recipe.recipe_id for recipe in recipes],
            documents=[tokenize(recipe_document(recipe)) for recipe in recipes],
        )

    def _score(self, query_tokens: list[str], index: int) -> float:
        if not self.documents or self._average_length == 0:
            return 0.0
        score = 0.0
        frequencies = self._frequencies[index]
        length = self._lengths[index]
        for token in query_tokens:
            frequency = frequencies.get(token, 0)
            if not frequency:
                continue
            denominator = frequency + self.k1 * (1 - self.b + self.b * length / self._average_length)
            score += self._idf.get(token, 0.0) * frequency * (self.k1 + 1) / denominator
        return score

    async def search(self, plan: QueryPlan, limit: int) -> list[RankedCandidate]:
        query_tokens = tokenize(plan.normalized_query)
        scored = [
            (self.recipe_ids[index], self._score(query_tokens, index))
            for index in range(len(self.recipe_ids))
        ]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return [
            RankedCandidate(recipe_id=recipe_id, score=score, source=self.name, reasons=["关键词匹配"])
            for recipe_id, score in scored[:limit]
            if score > 0
        ]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"version": 1, "recipe_ids": self.recipe_ids, "documents": self.documents},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "BM25Retriever":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("不支持的 BM25 索引版本")
        return cls(recipe_ids=payload["recipe_ids"], documents=payload["documents"])
