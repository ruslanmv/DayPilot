"""Token-bucket rate limiting + backpressure (batch B12).

Protects Ollabridge nodes and external APIs by capping tool-execution rate per
key (persona or provider). In-process buckets by default; a shared backend
(Redis) can back the same interface for multi-worker deployments.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    capacity: float
    tokens: float
    refill_per_sec: float
    updated: float


class RateLimiter:
    def __init__(self, rate_per_sec: float = 5.0, burst: float = 10.0) -> None:
        self.rate = rate_per_sec
        self.burst = burst
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, cost: float = 1.0) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(self.burst, self.burst, self.rate, now)
                self._buckets[key] = bucket
            elapsed = now - bucket.updated
            bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_per_sec)
            bucket.updated = now
            if bucket.tokens >= cost:
                bucket.tokens -= cost
                return True
            return False

    def retry_after(self, key: str, cost: float = 1.0) -> float:
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None or bucket.tokens >= cost:
                return 0.0
            deficit = cost - bucket.tokens
            return round(deficit / bucket.refill_per_sec, 3)
