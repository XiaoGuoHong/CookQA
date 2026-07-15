import json

from scripts.benchmark import (
    expected_ids,
    report_passed,
    run,
    summarize_case_diagnostics,
    summarize_latencies,
)


def test_latency_summary_reports_sample_count_and_p50_p95():
    summary = summarize_latencies([10.0, 20.0, 30.0, 40.0])

    assert summary == {
        "count": 4,
        "p50_ms": 20.0,
        "p95_ms": 40.0,
    }


def test_report_passed_requires_all_targets_and_zero_failures():
    report = {
        "targets": {"recall": True, "latency": True},
        "failures": [],
        "warmup_detail_failures": 0,
        "detail_failures": 0,
    }

    assert report_passed(report) is True

    report["targets"]["latency"] = False
    assert report_passed(report) is False
    report["targets"]["latency"] = True
    report["failures"] = [{"error_type": "http_error"}]
    assert report_passed(report) is False
    report["failures"] = []
    report["warmup_detail_failures"] = 1
    assert report_passed(report) is False
    report["warmup_detail_failures"] = 0
    report["detail_failures"] = 1
    assert report_passed(report) is False


def test_case_diagnostics_report_misses_intents_degradation_and_failures():
    diagnostics = summarize_case_diagnostics(
        [
            {
                "case_id": "case-001",
                "query": "可乐鸡翅怎么做",
                "expected_recipe_ids": ["expected-1"],
                "returned_recipe_ids": ["expected-1"],
                "expected_intent": "exact_recipe",
                "actual_intent": "exact_recipe",
                "hit": True,
                "degraded_components": [],
                "failure_category": None,
            },
            {
                "case_id": "case-002",
                "query": "推荐不辣的虾菜",
                "expected_recipe_ids": ["expected-2"],
                "returned_recipe_ids": ["actual-2"],
                "expected_intent": "conditional_recommendation",
                "actual_intent": "semantic_recommendation",
                "hit": False,
                "degraded_components": ["neo4j"],
                "failure_category": None,
            },
            {
                "case_id": "case-003",
                "query": "水煮鱼怎么做",
                "expected_recipe_ids": ["expected-3"],
                "returned_recipe_ids": [],
                "expected_intent": "exact_recipe",
                "actual_intent": None,
                "hit": False,
                "degraded_components": [],
                "failure_category": "http_status",
            },
        ]
    )

    assert diagnostics["misses"] == [
        {
            "case_id": "case-002",
            "query": "推荐不辣的虾菜",
            "expected_recipe_ids": ["expected-2"],
            "returned_recipe_ids": ["actual-2"],
            "expected_intent": "conditional_recommendation",
            "actual_intent": "semantic_recommendation",
        }
    ]
    assert diagnostics["intent_summary"]["conditional_recommendation"] == {
        "case_count": 1,
        "hit_count": 0,
        "miss_count": 1,
        "recall_at_5": 0.0,
    }
    assert diagnostics["degradation_summary"]["neo4j"] == {
        "case_count": 1,
        "case_ids": ["case-002"],
    }
    assert diagnostics["failure_summary"]["http_status"] == {
        "case_count": 1,
        "case_ids": ["case-003"],
    }


class _Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def iter_text(self):
        return iter(["chunk"])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _Client:
    def __init__(self, payload):
        self.response = _Response(payload)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def post(self, path, json):
        return self.response

    def stream(self, method, path, json):
        return self.response


def test_run_includes_diagnostics_and_uses_separate_cold_start_report(tmp_path, monkeypatch):
    case = {
        "query": "可乐鸡翅怎么做",
        "intent": "exact_recipe",
        "expected_recipe_paths": ["dishes/test.md"],
        "hard_constraints": {},
    }
    expected_id = next(iter(expected_ids(case)))
    payload = {
        "query_plan": {"intent": "exact_recipe"},
        "results": [{"recipe": {"recipe_id": expected_id}, "constraints_verified": True}],
        "degradation": {"unavailable_components": ["neo4j"]},
    }
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        "scripts.benchmark.httpx.Client",
        lambda **kwargs: _Client(payload),
    )

    report = run("http://testserver", cases_path, warmups=0, timeout=1)

    assert report["misses"] == []
    assert report["intent_summary"]["exact_recipe"]["hit_count"] == 1
    assert report["degradation_summary"]["neo4j"]["case_ids"] == ["case-001"]
    assert report["failure_summary"] == {}
    assert "cold_start_ms" not in report
