from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path

import httpx

from cookqa.ingest.normalize import stable_recipe_id


def percentile(values: list[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value / 100 * len(ordered)) - 1)
    return ordered[index]


def load_cases(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def expected_ids(case: dict) -> set[str]:
    return {stable_recipe_id(path) for path in case["expected_recipe_paths"]}


def violates_constraints(recipe: dict, constraints: dict) -> bool:
    ingredients = {item["name"] for item in recipe.get("ingredients", [])}
    tools = set(recipe.get("tools") or [])
    if any(item not in ingredients for item in constraints.get("required_ingredients", [])):
        return True
    if any(item in ingredients for item in constraints.get("excluded_ingredients", [])):
        return True
    if any(item in tools for item in constraints.get("excluded_tools", [])):
        return True
    if any(item not in tools for item in constraints.get("tools", [])):
        return True
    max_minutes = constraints.get("max_minutes")
    duration = recipe.get("duration_minutes")
    return bool(max_minutes is not None and (duration is None or duration > max_minutes))


def run(base_url: str, cases_path: Path, warmups: int, timeout: float) -> dict:
    cases = load_cases(cases_path)
    search_samples: list[float] = []
    first_token_samples: list[float] = []
    hits = 0
    hard_filter_violations = 0
    failures: list[dict] = []
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        for _ in range(warmups):
            client.post("/api/v1/search", json={"query": "家常菜"})
        for case in cases:
            started = time.perf_counter()
            response = client.post("/api/v1/search", json={"query": case["query"]})
            elapsed_ms = (time.perf_counter() - started) * 1000
            if response.status_code != 200:
                failures.append({"query": case["query"], "status": response.status_code})
                continue
            search_samples.append(elapsed_ms)
            payload = response.json()
            results = payload.get("results", [])
            returned_ids = {item["recipe"]["recipe_id"] for item in results[:5]}
            if expected_ids(case).intersection(returned_ids):
                hits += 1
            for item in results:
                if item.get("constraints_verified") and violates_constraints(
                    item["recipe"], case["hard_constraints"]
                ):
                    hard_filter_violations += 1

        detail_candidate = next(
            (
                item
                for case in cases
                for item in [client.post("/api/v1/search", json={"query": case["query"]})]
                if item.status_code == 200 and item.json().get("results")
            ),
            None,
        )
        if detail_candidate is not None:
            recipe_id = detail_candidate.json()["results"][0]["recipe"]["recipe_id"]
            for _ in range(5):
                started = time.perf_counter()
                with client.stream(
                    "POST",
                    f"/api/v1/recipes/{recipe_id}/answer/stream",
                    json={"question": "请简要说明做法"},
                ) as response:
                    if response.status_code != 200:
                        break
                    first_chunk = next(response.iter_text(), "")
                    if first_chunk:
                        first_token_samples.append((time.perf_counter() - started) * 1000)

    evaluated = len(cases) - len(failures)
    search_p95 = percentile(search_samples, 95)
    first_token_p95 = percentile(first_token_samples, 95)
    return {
        "case_count": len(cases),
        "evaluated_count": evaluated,
        "recall_at_5": hits / evaluated if evaluated else None,
        "hard_filter_violations": hard_filter_violations,
        "search_p95_ms": search_p95,
        "search_mean_ms": statistics.fmean(search_samples) if search_samples else None,
        "first_token_p95_ms": first_token_p95,
        "cold_start_ms": None,
        "targets": {
            "recall_at_5_ge_0_90": evaluated == len(cases) and hits / evaluated >= 0.9
            if evaluated
            else False,
            "hard_filter_violations_eq_0": hard_filter_violations == 0,
            "search_p95_le_1000_ms": search_p95 is not None and search_p95 <= 1000,
            "first_token_p95_le_3000_ms": first_token_p95 is not None and first_token_p95 <= 3000,
        },
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CookQA warmed local benchmark")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cases", type=Path, default=Path("evaluation/queries.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("Data/runtime/benchmark-report.json"))
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    report = run(args.base_url, args.cases, args.warmups, args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
