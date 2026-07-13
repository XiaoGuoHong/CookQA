import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_evaluation_set_has_required_coverage_and_schema():
    cases = load_jsonl(ROOT / "evaluation" / "queries.jsonl")
    intents = Counter(case["intent"] for case in cases)

    assert len(cases) >= 50
    assert set(intents) == {
        "exact_recipe",
        "ingredient_lookup",
        "conditional_recommendation",
        "semantic_recommendation",
        "similar_recipe",
        "recipe_comparison",
    }
    assert all(case["query"].strip() for case in cases)
    assert all(case["expected_recipe_paths"] for case in cases)
    assert all(isinstance(case["hard_constraints"], dict) for case in cases)
    assert len({case["query"] for case in cases}) == len(cases)


def test_fixed_selection_contains_exactly_200_supported_recipe_paths():
    path = ROOT / "config" / "recipe-selection-mvp.txt"
    entries = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    assert len(entries) == 200
    assert len(set(entries)) == 200
    assert not any(
        f"dishes/{excluded}/" in entry
        for entry in entries
        for excluded in ("condiment", "dessert", "drink", "semi-finished", "template")
    )


def test_source_manifest_pins_a_git_commit():
    manifest = json.loads((ROOT / "config" / "howtocook-source.json").read_text(encoding="utf-8"))

    assert manifest["repository"] == "https://github.com/Anduin2017/HowToCook.git"
    assert len(manifest["commit"]) == 40
