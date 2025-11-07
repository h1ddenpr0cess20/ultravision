from __future__ import annotations

import time

from ultravision import util


def test_backoff_sleep_respects_cap(monkeypatch):
    calls = []

    def fake_sleep(duration):
        calls.append(duration)

    monkeypatch.setattr(util.time, "sleep", fake_sleep)
    util.backoff_sleep(attempt=1, base=2, cap=10)
    util.backoff_sleep(attempt=5, base=2, cap=5)
    assert calls[0] == 2  # 2 ** 1
    assert calls[1] == 5  # capped at 5 rather than 32


def test_run_concurrently_serial_mode():
    results = []

    def add(a, b):
        return a + b

    util.run_concurrently(add, [(1, 2), (3, 4)], max_workers=1, on_result=lambda r: results.append(r))
    assert results == [3, 7]


def test_run_concurrently_parallel_mode():
    seen = []

    def worker(delay, value):
        time.sleep(delay)
        return value

    jobs = [(0.05, "slow"), (0.01, "fast"), (0.02, "mid")]
    util.run_concurrently(worker, jobs, max_workers=3, on_result=lambda res: seen.append(res))

    assert set(seen) == {"slow", "fast", "mid"}
