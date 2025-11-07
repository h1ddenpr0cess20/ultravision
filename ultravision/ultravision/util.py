"""Lightweight utilities for retries and concurrent batch execution."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def backoff_sleep(attempt: int, base: float = 1.7, cap: float = 25.0):
    """Sleep for a backoff interval before retrying a failed batch.

    Args:
        attempt (int): Retry attempt number (typically starts at 1).
        base (float): Base multiplier, used as ``base ** attempt``.
        cap (float): Maximum number of seconds to sleep.
    """
    time.sleep(min(cap, base ** attempt))

def run_concurrently(func, jobs, max_workers: int, on_result):
    """Dispatch jobs to a thread pool and stream results via a callback.

    Args:
        func: Callable that processes a single job tuple.
        jobs: Iterable of job parameter tuples fed to ``func``.
        max_workers (int): Maximum number of concurrent threads.
        on_result: Callback that receives each function result as it completes.
    """
    if max_workers <= 1:
        for job in jobs:
            on_result(func(*job))
        return

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_map = {ex.submit(func, *job): job for job in jobs}
        for fut in as_completed(future_map):
            res = fut.result()
            on_result(res)
