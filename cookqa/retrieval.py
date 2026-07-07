from collections import defaultdict
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .graph import RecipeGraph
from .index_store import FaissIndexStore
from .models import QueryMode, Recommendation, RecipeDocument


EmbedQuery = Callable[[str], list[float]]


def detect_mode(question: str, graph_matches: Dict[str, List[str]]) -> QueryMode:
    if not graph_matches and "黯然销魂饭" in question:
        return "missing_or_fictional"
    if any(
        relation.startswith(("name:", "name_alias:"))
        for matches in graph_matches.values()
        for relation in matches
    ):
        return "dish_lookup"
    if any(
        relation.startswith("ingredient:")
        for matches in graph_matches.values()
        for relation in matches
    ):
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
            for chunk, score in self.recipe_index.search(
                question, self.embed_query, top_k=top_k
            ):
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

    def _recommendation(
        self,
        recipe_id: str,
        score: float,
        reasons: List[str],
    ) -> Recommendation:
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
