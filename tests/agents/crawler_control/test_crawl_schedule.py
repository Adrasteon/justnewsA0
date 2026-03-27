from datetime import UTC, datetime
from pathlib import Path

from agents.crawler_control.crawl_schedule import (
    CrawlCadence,
    CrawlRun,
    load_crawl_schedule,
)
from scripts.ops.run_crawl_schedule import _effective_limit


def _write_schedule(path: Path) -> None:
    path.write_text(
        """
version: 1
metadata:
  stage: B1
  owner: tests
global:
  target_articles_per_hour: 120
  default_max_articles_per_site: 40
  default_concurrent_sites: 2
runs:
  - name: high-priority
    enabled: true
    priority: 10
    cadence:
      every_hours: 2
      minute_offset: 0
    domains:
      - example.com
      - example.org
  - name: secondary
    enabled: true
    priority: 20
    cadence:
      every_hours: 1
      minute_offset: 15
    domains:
      - news.example
  - name: disabled
    enabled: false
    cadence:
      every_hours: 1
    domains:
      - ignore.me
        """.strip()
    )


def test_load_crawl_schedule_filters_and_sorts(tmp_path: Path) -> None:
    schedule_path = tmp_path / "schedule.yaml"
    _write_schedule(schedule_path)

    schedule = load_crawl_schedule(schedule_path)
    reference = datetime(2024, 4, 1, 10, 0, tzinfo=UTC)
    due_runs = schedule.due_runs(reference)

    assert [run.name for run in due_runs] == ["high-priority", "secondary"]
    assert due_runs[0].cadence.minute_offset == 0
    assert due_runs[1].cadence.minute_offset == 15


def test_effective_limit_respects_remaining_budget() -> None:
    run = CrawlRun(
        name="sample",
        domains=["example.com", "example.org"],
        cadence=CrawlCadence(),
        max_articles_per_site=40,
        concurrent_sites=2,
    )

    assert _effective_limit(remaining=200, run=run) == 40
    assert _effective_limit(remaining=80, run=run) == 40
    assert _effective_limit(remaining=70, run=run) == 35
    assert _effective_limit(remaining=1, run=run) == 0
    assert _effective_limit(remaining=0, run=run) == 0
