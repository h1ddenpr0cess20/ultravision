import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def backoff_sleep(attempt: int, base: float = 1.7, cap: float = 25.0):
    time.sleep(min(cap, base ** attempt))

def run_concurrently(func, jobs, max_workers: int, on_result):
    # Run callables concurrently and deliver results to the on_result callback.
    if max_workers <= 1:
        for job in jobs:
            on_result(func(*job))
        return

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_map = {ex.submit(func, *job): job for job in jobs}
        for fut in as_completed(future_map):
            res = fut.result()
            on_result(res)
