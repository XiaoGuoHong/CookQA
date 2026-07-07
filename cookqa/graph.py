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
        for relation, recipe_ids in self.relations.items():
            _, value = relation.split(":", 1)
            candidate_terms = _normalize_terms(value)
            if any(term and term in question for term in candidate_terms):
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
