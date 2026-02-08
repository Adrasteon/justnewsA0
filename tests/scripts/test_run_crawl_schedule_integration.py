from __future__ import annotations

import json
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.ops import run_crawl_schedule

SCHEDULE_YAML = """\
version: 1
metadata:
  stage: B
  owner: tests
global:
  target_articles_per_hour: 12
  default_max_articles_per_site: 6
  default_timeout_seconds: 30
  strategy: standard
  enable_ai_enrichment: true
  governance:
    controls:
      - name: policy
        description: mocked
runs:
  - name: primary
    enabled: true
    priority: 5
    cadence:
      every_hours: 1
      minute_offset: 0
    domains:
      - example.com
      - example.net
"""


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if not (200 <= self.status_code < 300):
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._payload


class RequestRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, json: dict[str, Any], timeout: int) -> FakeResponse:
        call = {"url": url, "json": json, "timeout": timeout}
        self.calls.append(call)
        return FakeResponse({"job_id": f"job-{len(self.calls)}"})

    def get(self, url: str, timeout: int) -> FakeResponse:
        payload = {
            "status": "completed",
            "result": {
                "articles_ingested": 5,
                "domains": ["example.com"],
            },
        }
        return FakeResponse(payload)


@pytest.fixture()
def requests_stub(monkeypatch: pytest.MonkeyPatch) -> RequestRecorder:
    recorder = RequestRecorder()
    monkeypatch.setattr("scripts.ops.run_crawl_schedule.requests.post", recorder.post)
    monkeypatch.setattr("scripts.ops.run_crawl_schedule.requests.get", recorder.get)
    return recorder


def write_schedule(path: Path) -> None:
    path.write_text(SCHEDULE_YAML, encoding="utf-8")


def run_scheduler(
    tmp_path: Path, dry_run: bool = False
) -> tuple[int, Path, Path, Path]:
    schedule_path = tmp_path / "crawl_schedule.yaml"
    state_path = tmp_path / "state.json"
    success_path = tmp_path / "success.json"
    metrics_path = tmp_path / "metrics.prom"

    write_schedule(schedule_path)

    args = Namespace(
        schedule=schedule_path,
        state_output=state_path,
        success_output=success_path,
        metrics_output=metrics_path,
        crawler_url="http://fake-crawler",
        dry_run=dry_run,
        no_wait=True,
        max_target=None,
        timeout=None,
        testrun=True,
        db_limit=None,
        db_chunk_size=10,
        NoFollow=None,
    )

    reference_time = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)

    # Patch argument parsing and clock helpers so the scheduler runs deterministically.
    def _patched_parse_args() -> Namespace:
        return args

    def _patched_now() -> datetime:
        return reference_time

    patcher = pytest.MonkeyPatch()
    patcher.setattr("scripts.ops.run_crawl_schedule._parse_args", _patched_parse_args)
    patcher.setattr("scripts.ops.run_crawl_schedule._now", _patched_now)

    try:
        exit_code = run_crawl_schedule.main()
    finally:
        patcher.undo()

    return exit_code, state_path, success_path, metrics_path


@pytest.mark.parametrize("dry_run", [True, False])
def test_scheduler_invokes_crawler_and_writes_outputs(
    tmp_path: Path, requests_stub: RequestRecorder, dry_run: bool
) -> None:
    exit_code, state_path, success_path, metrics_path = run_scheduler(
        tmp_path, dry_run=dry_run
    )

    assert exit_code == 0

    state = json.loads(state_path.read_text(encoding="utf-8"))
    runs = state["runs"]
    assert runs and runs[0]["name"] == "primary"
    assert state["target_articles"] == 12
    assert state["governance"]["controls"][0]["name"] == "policy"

    if dry_run:
        assert not requests_stub.calls
        assert not success_path.exists()
    else:
        assert len(requests_stub.calls) == 1
        call = requests_stub.calls[0]
        assert call["url"] == "http://fake-crawler/unified_production_crawl"
        assert call["json"]["kwargs"]["max_articles_per_site"] == 6

        success = json.loads(success_path.read_text(encoding="utf-8"))
        assert success[0]["total_articles"] == 5

    metrics = metrics_path.read_text(encoding="utf-8")
    assert "justnews_crawler_scheduler_articles_accepted_total" in metrics
