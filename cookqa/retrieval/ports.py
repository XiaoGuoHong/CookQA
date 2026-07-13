from __future__ import annotations

from typing import Protocol

from cookqa.models import QueryPlan, RankedCandidate


class RankedRetriever(Protocol):
    name: str

    async def search(self, plan: QueryPlan, limit: int) -> list[RankedCandidate]: ...


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float]: ...
