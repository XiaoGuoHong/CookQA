import asyncio

import numpy as np

from cookqa.models import QueryPlan
from cookqa.retrieval.faiss_store import FaissRetriever, FaissVectorIndex


class FailingEmbedder:
    async def embed(self, text):
        raise AssertionError("similar recipe lookup must reuse the indexed reference vector")


def test_similar_recipe_reuses_indexed_reference_vector():
    vector_index = FaissVectorIndex.build(
        recipe_ids=["reference", "similar", "unrelated"],
        vectors=np.array(
            [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]],
            dtype=np.float32,
        ),
    )
    retriever = FaissRetriever(
        vector_index,
        FailingEmbedder(),
        reference_recipe_ids={"Reference Recipe": "reference"},
    )
    plan = QueryPlan(
        original_query="find recipes similar to Reference Recipe",
        normalized_query="find recipes similar to Reference Recipe",
        intent="similar_recipe",
        recognized_recipes=["Reference Recipe"],
        retrieval_strategy=["faiss"],
        confidence=0.95,
    )

    candidates = asyncio.run(retriever.search(plan, limit=3))

    assert [candidate.recipe_id for candidate in candidates] == [
        "reference",
        "similar",
        "unrelated",
    ]
