"""In-process sliding-window rate limiting.

Counters live in this process's memory. That matches the current deployment
(one uvicorn process). Running several workers or replicas would give each
its own counters, so the effective limit would multiply; a shared store
would be needed then. Counters reset when the API restarts.
"""

import threading
import time
from collections import deque


class SlidingWindowRateLimiter:
    # Above this many tracked keys, expired ones are swept on the next hit.
    _SWEEP_THRESHOLD = 10_000

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        """Records one attempt for `key`. Returns False, without recording,
        when `limit` attempts already fall inside the window."""
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            if len(self._events) > self._SWEEP_THRESHOLD:
                self._sweep(cutoff)

            events = self._events.setdefault(key, deque())

            while events and events[0] <= cutoff:
                events.popleft()

            if len(events) >= limit:
                return False

            events.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def _sweep(self, cutoff: float) -> None:
        for key in [
            key
            for key, events in self._events.items()
            if not events or events[-1] <= cutoff
        ]:
            del self._events[key]


password_rate_limiter = SlidingWindowRateLimiter()
