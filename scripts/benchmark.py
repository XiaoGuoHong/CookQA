from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path

import httpx

from cookqa.ingest.normalize import stable_recipe_id
from cookqa.retrieval.fusion import recipe_has_label


def percentile(values: list[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value / 100 * len(ordered)) - 1)
    return ordered[index]


def summarize_latencies(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "p50_ms": percentile(values, 50),
        "p95_ms": percentile(values, 95),
    }


def report_passed(report: dict) -> bool:
    return bool(
        report.get("targets")
        and all(report["targets"].values())
        and not report.get("failures")
        and report.get("warmup_detail_failures") == 0
        and report.get("detail_failures") == 0
    )


def load_cases(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def expected_ids(case: dict) -> set[str]:
    return {stable_recipe_id(path) for path in case["expected_recipe_paths"]}


def case_id(case: dict, index: int) -> str:
    return str(case.get("id") or f"case-{index:03d}")


def summarize_case_diagnostics(records: list[dict]) -> dict:
    misses: list[dict] = []
    intent_summary: dict[str, dict] = {}
    degradation_summary: dict[str, dict] = {}
    failure_summary: dict[str, dict] = {}

    for record in sorted(records, key=lambda item: item["case_id"]):
        identifier = record["case_id"]
        intent = record["expected_intent"]
        intent_bucket = intent_summary.setdefault(
            intent,
            {"case_count": 0, "hit_count": 0, "miss_count": 0},
        )
        intent_bucket["case_count"] += 1
        if record["hit"]:
            intent_bucket["hit_count"] += 1
        else:
            intent_bucket["miss_count"] += 1
            if record["failure_category"] is None:
                misses.append(
                    {
                        "case_id": identifier,
                        "query": record["query"],
                        "expected_recipe_ids": record["expected_recipe_ids"],
                        "returned_recipe_ids": record["returned_recipe_ids"],
                        "expected_intent": intent,
                        "actual_intent": record["actual_intent"],
                    }
                )

        for component in record["degraded_components"]:
            bucket = degradation_summary.setdefault(component, {"case_ids": []})
            bucket["case_ids"].append(identifier)

        category = record["failure_category"]
        if category is not None:
            bucket = failure_summary.setdefault(category, {"case_ids": []})
            bucket["case_ids"].append(identifier)

    for bucket in intent_summary.values():
        bucket["recall_at_5"] = bucket["hit_count"] / bucket["case_count"]
    for summary in (degradation_summary, failure_summary):
        for bucket in summary.values():
            bucket["case_count"] = len(bucket["case_ids"])

    return {
        "misses": misses,
        "intent_summary": dict(sorted(intent_summary.items())),
        "degradation_summary": dict(sorted(degradation_summary.items())),
        "failure_summary": dict(sorted(failure_summary.items())),
    }


def violates_constraints(recipe: dict, constraints: dict) -> bool:
    ingredients = {item["name"].casefold() for item in recipe.get("ingredients", [])}
    searchable = ingredients | {str(recipe.get("name", "")).casefold()}
    equivalents = {
        "\u732a\u8089": ("\u732a\u8089", "\u4e94\u82b1\u8089"),
        "\u867e": ("\u867e", "\u5927\u867e", "\u867e\u4ec1", "\u7f57\u6c0f\u867e"),
        "\u7c73\u996d": ("\u7c73\u996d", "\u996d"),
    }

    def matches(item: str) -> bool:
        return any(
            candidate.casefold() in value
            for candidate in equivalents.get(item, (item,))
            for value in searchable
        )

    if any(not matches(item) for item in constraints.get("required_ingredients", [])):
        return True
    if any(matches(item) for item in constraints.get("excluded_ingredients", [])):
        return True
    tools = {str(item).casefold() for item in recipe.get("tools") or []}
    name = str(recipe.get("name", "")).casefold()
    if any(
        item.casefold() in tools or item.casefold() in name
        for item in constraints.get("excluded_tools", [])
    ):
        return True
    if any(
        item.casefold() not in tools and item.casefold() not in name
        for item in constraints.get("tools", [])
    ):
        return True
    category = constraints.get("category")
    if category:
        categories = {str(item).casefold() for item in recipe.get("categories") or []}
        source_path = str(recipe.get("source_path", "")).casefold()
        if (
            category.casefold() not in categories
            and f"/{category.casefold()}/" not in f"/{source_path}"
        ):
            return True
    if "\u8fa3" in constraints.get("excluded_ingredients", []) and recipe_has_label(
        recipe, "spicy"
    ):
        return True
    if "\u8fa3" in constraints.get("required_ingredients", []) and not recipe_has_label(
        recipe, "spicy"
    ):
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
    case_records: list[dict] = []
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        for _ in range(warmups):
            client.post("/api/v1/search", json={"query": "家常菜"})
        for index, case in enumerate(cases, start=1):
            identifier = case_id(case, index)
            expected = expected_ids(case)
            record = {
                "case_id": identifier,
                "query": case["query"],
                "expected_recipe_ids": sorted(expected),
                "returned_recipe_ids": [],
                "expected_intent": case["intent"],
                "actual_intent": None,
                "hit": False,
                "degraded_components": [],
                "failure_category": None,
            }
            started = time.perf_counter()
            try:
                response = client.post("/api/v1/search", json={"query": case["query"]})
            except httpx.HTTPError:
                record["failure_category"] = "http_error"
                case_records.append(record)
                failures.append(
                    {"case_id": identifier, "query": case["query"], "error_type": "http_error"}
                )
                continue
            elapsed_ms = (time.perf_counter() - started) * 1000
            if response.status_code != 200:
                record["failure_category"] = "http_status"
                case_records.append(record)
                failures.append(
                    {
                        "case_id": identifier,
                        "query": case["query"],
                        "status": response.status_code,
                    }
                )
                continue
            try:
                payload = response.json()
                results = payload.get("results", [])
                returned_ids = [item["recipe"]["recipe_id"] for item in results[:5]]
            except (KeyError, TypeError, ValueError):
                record["failure_category"] = "invalid_response"
                case_records.append(record)
                failures.append(
                    {
                        "case_id": identifier,
                        "query": case["query"],
                        "error_type": "invalid_response",
                    }
                )
                continue
            hit = bool(expected.intersection(returned_ids))
            record.update(
                {
                    "returned_recipe_ids": returned_ids,
                    "actual_intent": payload.get("query_plan", {}).get("intent"),
                    "hit": hit,
                    "degraded_components": sorted(
                        payload.get("degradation", {}).get("unavailable_components") or []
                    ),
                }
            )
            case_records.append(record)
            search_samples.append(elapsed_ms)
            if hit:
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
        warmup_detail_failures = 0
        detail_failures = 0
        if detail_candidate is not None:
            recipe_id = detail_candidate.json()["results"][0]["recipe"]["recipe_id"]
            for _ in range(2):
                try:
                    with client.stream(
                        "POST",
                        f"/api/v1/recipes/{recipe_id}/answer/stream",
                        json={"question": "\u8bf7\u7b80\u8981\u8bf4\u660e\u505a\u6cd5"},
                    ) as response:
                        if response.status_code != 200:
                            warmup_detail_failures += 1
                            continue
                        next(response.iter_text(), "")
                except httpx.HTTPError:
                    warmup_detail_failures += 1
            for _ in range(5):
                started = time.perf_counter()
                try:
                    with client.stream(
                        "POST",
                        f"/api/v1/recipes/{recipe_id}/answer/stream",
                        json={"question": "\u8bf7\u7b80\u8981\u8bf4\u660e\u505a\u6cd5"},
                    ) as response:
                        if response.status_code != 200:
                            detail_failures += 1
                            continue
                        first_chunk = next(response.iter_text(), "")
                        if first_chunk:
                            first_token_samples.append((time.perf_counter() - started) * 1000)
                        else:
                            detail_failures += 1
                except httpx.HTTPError:
                    detail_failures += 1

    diagnostics = summarize_case_diagnostics(case_records)
    for category, count in (
        ("warmup_detail", warmup_detail_failures if detail_candidate is not None else 0),
        ("detail", detail_failures if detail_candidate is not None else 0),
    ):
        if count:
            diagnostics["failure_summary"][category] = {
                "case_count": count,
                "case_ids": [],
            }
    diagnostics["failure_summary"] = dict(sorted(diagnostics["failure_summary"].items()))
    evaluated = len(cases) - len(failures)
    search_summary = summarize_latencies(search_samples)
    first_token_summary = summarize_latencies(first_token_samples)
    return {
        "case_count": len(cases),
        "evaluated_count": evaluated,
        "recall_at_5": hits / evaluated if evaluated else None,
        "hard_filter_violations": hard_filter_violations,
        "misses": diagnostics["misses"],
        "intent_summary": diagnostics["intent_summary"],
        "degradation_summary": diagnostics["degradation_summary"],
        "failure_summary": diagnostics["failure_summary"],
        "search_samples": search_summary,
        "first_token_samples": first_token_summary,
        "search_p50_ms": search_summary["p50_ms"],
        "search_p95_ms": search_summary["p95_ms"],
        "search_mean_ms": statistics.fmean(search_samples) if search_samples else None,
        "first_token_p50_ms": first_token_summary["p50_ms"],
        "first_token_p95_ms": first_token_summary["p95_ms"],
        "warmup_detail_failures": warmup_detail_failures if detail_candidate is not None else 0,
        "detail_failures": detail_failures if detail_candidate is not None else 0,
        "targets": {
            "recall_at_5_ge_0_90": evaluated == len(cases) and hits / evaluated >= 0.9
            if evaluated
            else False,
            "hard_filter_violations_eq_0": hard_filter_violations == 0,
            "search_p95_le_1000_ms": search_summary["p95_ms"] is not None
            and search_summary["p95_ms"] <= 1000,
            "first_token_p95_le_3000_ms": first_token_summary["p95_ms"] is not None
            and first_token_summary["p95_ms"] <= 3000,
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
    return 0 if report_passed(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
