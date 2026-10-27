"""Fixed-window rate limiters keyed by client IP.
RateLimiter (default) keeps state in process memory: simple, but the limit multiplies with several workers/instances.
DatabaseRateLimiter keeps counters in the application database so every instance shares one limit (RATE_LIMIT_BACKEND=database)."""
import hashlib
import time
from collections import defaultdict
from threading import Lock


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
        self._lock = Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        if self.per_minute <= 0:
            return True, 0
        now = int(time.time())
        window = now // 60
        with self._lock:
            w, n = self._hits[key]
            if w != window:
                w, n = window, 0
            if n >= self.per_minute:
                return False, 60 - (now % 60)
            self._hits[key] = (w, n + 1)
            if len(self._hits) > 10000:  # bound memory
                self._hits = defaultdict(lambda: (0, 0), {k: v for k, v in self._hits.items() if v[0] == window})
        return True, 0


class DatabaseRateLimiter:
    """Same contract as RateLimiter but counters live in the database, so the limit holds across workers/instances."""

    def __init__(self, session_factory, per_minute: int):
        self.sf, self.per_minute = session_factory, per_minute

    def check(self, key: str) -> tuple[bool, int]:
        if self.per_minute <= 0:
            return True, 0
        from sqlalchemy import delete
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        from .db.models import RateLimitBucket as B
        now = int(time.time())
        window = now // 60
        hk = hashlib.sha256(key.encode()).hexdigest()
        with self.sf() as db:
            insert_fn = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
            stmt = (insert_fn(B).values(key=hk, window=window, count=1)
                    .on_conflict_do_update(index_elements=[B.key, B.window], set_={"count": B.count + 1}).returning(B.count))
            count = db.execute(stmt).scalar_one()
            if count == 1:                                   # first hit of a bucket: tidy old windows
                db.execute(delete(B).where(B.window < window - 5))
            db.commit()
        if count > self.per_minute:
            return False, 60 - (now % 60)
        return True, 0
