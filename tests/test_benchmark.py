from scripts.benchmark import summarize_latencies


def test_latency_summary_reports_sample_count_and_p50_p95():
    summary = summarize_latencies([10.0, 20.0, 30.0, 40.0])

    assert summary == {
        "count": 4,
        "p50_ms": 20.0,
        "p95_ms": 40.0,
    }
