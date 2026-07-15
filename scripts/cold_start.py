from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from scripts.benchmark import summarize_latencies

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _stop_process(process: Any) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def measure_sample(
    command: list[str],
    base_url: str,
    timeout: float,
    query: str,
    *,
    popen_factory: Callable[..., Any] = subprocess.Popen,
    client_factory: Callable[..., Any] = httpx.Client,
    clock: Callable[[], float] = time.perf_counter,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    try:
        process = popen_factory(
            command,
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return {"status": "failed", "stage": "startup", "error_type": "process_start"}

    started = clock()
    try:
        with client_factory(base_url=base_url, timeout=min(timeout, 1.0)) as client:
            while True:
                if process.poll() is not None:
                    return {
                        "status": "failed",
                        "stage": "startup",
                        "error_type": "process_exit",
                    }
                if clock() - started >= timeout:
                    return {
                        "status": "failed",
                        "stage": "ready",
                        "error_type": "ready_timeout",
                    }
                try:
                    response = client.get("/ready")
                except httpx.HTTPError:
                    sleeper(0.1)
                    continue
                if response.status_code == 200:
                    ready_ms = round((clock() - started) * 1000, 2)
                    break
                sleeper(0.1)

            search_started = clock()
            try:
                response = client.post("/api/v1/search", json={"query": query})
            except httpx.HTTPError:
                return {
                    "status": "failed",
                    "stage": "search",
                    "error_type": "client_error",
                }
            if response.status_code != 200:
                return {
                    "status": "failed",
                    "stage": "search",
                    "error_type": "search_http",
                }
            return {
                "status": "ok",
                "ready_ms": ready_ms,
                "first_search_ms": round((clock() - search_started) * 1000, 2),
            }
    finally:
        _stop_process(process)


def summarize_samples(samples: list[dict]) -> dict:
    successful = [sample for sample in samples if sample["status"] == "ok"]
    ready_values = [float(sample["ready_ms"]) for sample in successful]
    search_values = [float(sample["first_search_ms"]) for sample in successful]
    return {
        "sample_count": len(samples),
        "success_count": len(successful),
        "failure_count": len(samples) - len(successful),
        "ready_samples": summarize_latencies(ready_values),
        "first_search_samples": summarize_latencies(search_values),
        "samples": samples,
        "targets": {
            "all_samples_succeeded": bool(samples) and len(successful) == len(samples),
        },
    }


def available_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind((host, 0))
        return int(server.getsockname()[1])


def run_samples(sample_count: int, timeout: float, query: str) -> dict:
    samples = []
    for _ in range(sample_count):
        port = available_port()
        samples.append(
            measure_sample(
                [
                    sys.executable,
                    "-m",
                    "cookqa.cli",
                    "serve",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                f"http://127.0.0.1:{port}",
                timeout,
                query,
            )
        )
    return summarize_samples(samples)


def main() -> int:
    parser = argparse.ArgumentParser(description="CookQA API cold-start benchmark")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--query", default="可乐鸡翅怎么做")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("Data/runtime/cold-start-report.json"),
    )
    args = parser.parse_args()
    if args.samples <= 0:
        parser.error("--samples must be greater than zero")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    report = run_samples(args.samples, args.timeout, args.query)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["targets"]["all_samples_succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
