import asyncio
import os
import time
from types import SimpleNamespace

from agents.crawler.crawler_engine import CrawlerEngine


class FakeProc:
    def __init__(self, pid, name, cmdline, create_time, parents_pids):
        self.info = {
            "pid": pid,
            "name": name,
            "cmdline": cmdline.split() if isinstance(cmdline, str) else cmdline,
            "create_time": create_time,
        }
        self._parents_pids = parents_pids
        self.terminated = False

    def parents(self):
        return [SimpleNamespace(pid=p) for p in self._parents_pids]

    def terminate(self):
        self.terminated = True


async def run_cleanup_with_psutil(monkeypatch, procs):
    async def fake_proc_iter(attrs=None):
        for p in procs:
            yield p

    monkeypatch.setattr("psutil.process_iter", lambda attrs=None: iter(procs))
    crawler = CrawlerEngine()
    await crawler._cleanup_orphaned_processes()


def test_cleanup_terminates_descendants(monkeypatch):
    now_ts = time.time()
    current_pid = os.getpid()
    # descendant process older than threshold
    p1 = FakeProc(
        pid=9999,
        name="chrome",
        cmdline="chrome",
        create_time=now_ts - 1200,
        parents_pids=[current_pid],
    )
    # non-descendant process should not be killed
    p2 = FakeProc(
        pid=8888,
        name="chrome",
        cmdline="chrome",
        create_time=now_ts - 1200,
        parents_pids=[1],
    )
    asyncio.run(run_cleanup_with_psutil(monkeypatch, [p1, p2]))
    assert p1.terminated is True
    assert p2.terminated is False
