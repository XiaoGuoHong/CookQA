import subprocess
import sys
from pathlib import Path

from scripts.cold_start import measure_sample, summarize_samples


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class FakeClient:
    def __init__(self, get_statuses, post_status=200):
        self.get_statuses = iter(get_statuses)
        self.post_status = post_status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def get(self, path):
        return FakeResponse(next(self.get_statuses))

    def post(self, path, json):
        return FakeResponse(self.post_status)


class FakeProcess:
    def __init__(self, return_code=None):
        self.return_code = return_code
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.return_code

    def terminate(self):
        self.terminated = True

    def wait(self, timeout):
        self.return_code = 0
        return self.return_code

    def kill(self):
        self.killed = True


def sample_with(process, client, times, timeout=1.0):
    return measure_sample(
        ["python", "-m", "cookqa.cli", "serve"],
        "http://127.0.0.1:8001",
        timeout,
        "可乐鸡翅怎么做",
        popen_factory=lambda *args, **kwargs: process,
        client_factory=lambda **kwargs: client,
        clock=iter(times).__next__,
        sleeper=lambda seconds: None,
    )


def test_measure_sample_records_ready_and_first_search_latency():
    process = FakeProcess()
    client = FakeClient(get_statuses=[503, 200])

    sample = sample_with(process, client, [0.0, 0.1, 0.2, 0.25, 0.25, 0.29])

    assert sample == {
        "status": "ok",
        "ready_ms": 250.0,
        "first_search_ms": 40.0,
    }
    assert process.terminated is True
    assert process.killed is False


def test_measure_sample_reports_ready_timeout_and_terminates_process():
    process = FakeProcess()
    client = FakeClient(get_statuses=[])

    sample = sample_with(process, client, [0.0, 1.1])

    assert sample == {
        "status": "failed",
        "stage": "ready",
        "error_type": "ready_timeout",
    }
    assert process.terminated is True


def test_measure_sample_reports_process_exit_before_ready():
    process = FakeProcess(return_code=1)
    client = FakeClient(get_statuses=[])

    sample = sample_with(process, client, [0.0])

    assert sample == {
        "status": "failed",
        "stage": "startup",
        "error_type": "process_exit",
    }
    assert process.terminated is False


def test_measure_sample_reports_first_search_http_failure():
    process = FakeProcess()
    client = FakeClient(get_statuses=[200], post_status=503)

    sample = sample_with(process, client, [0.0, 0.1, 0.2, 0.2])

    assert sample == {
        "status": "failed",
        "stage": "search",
        "error_type": "search_http",
    }
    assert process.terminated is True


def test_summarize_samples_reports_counts_percentiles_and_target():
    report = summarize_samples(
        [
            {"status": "ok", "ready_ms": 100.0, "first_search_ms": 20.0},
            {"status": "ok", "ready_ms": 200.0, "first_search_ms": 40.0},
            {"status": "failed", "stage": "ready", "error_type": "ready_timeout"},
        ]
    )

    assert report["sample_count"] == 3
    assert report["success_count"] == 2
    assert report["failure_count"] == 1
    assert report["ready_samples"] == {"count": 2, "p50_ms": 100.0, "p95_ms": 200.0}
    assert report["first_search_samples"] == {
        "count": 2,
        "p50_ms": 20.0,
        "p95_ms": 40.0,
    }
    assert report["targets"]["all_samples_succeeded"] is False


def test_cold_start_script_can_run_directly():
    project_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [sys.executable, "scripts/cold_start.py", "--help"],
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "CookQA API cold-start benchmark" in result.stdout
