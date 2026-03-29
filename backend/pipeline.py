import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from buffer import IngestBuffer, BufferedLog
from storage.clickhouse_store import ClickHouseStore
from storage.postgres_store import PostgresStore

logger = logging.getLogger(__name__)

HOT_THRESHOLD_HOURS = 24
WARM_THRESHOLD_DAYS = 30

SOURCE_REGIONS = {
    'api-service': 'us-west-2',
    'worker-service': 'us-east-1',
    'cache-service': 'eu-west-1',
    'auth-service': 'us-west-2',
    'db-service': 'us-east-1',
}


def compute_hash(source: str, level: str, message: str) -> int:
    raw = f'{source}:{level}:{message}'
    return int(hashlib.md5(raw.encode()).hexdigest()[:16], 16)


class ProcessingPipeline:
    def __init__(self, buffer: IngestBuffer, hot: ClickHouseStore, warm: PostgresStore):
        self._buffer = buffer
        self._hot = hot
        self._warm = warm
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._dedup_window: dict[int, float] = {}
        self._dedup_ttl = 0.1
        self._processed = 0
        self._deduplicated = 0
        self._latencies: list[float] = []

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info('Processing pipeline started')

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info('Processing pipeline stopped')

    async def _run(self):
        while self._running:
            try:
                batch = await self._buffer.drain(1000)
                if batch:
                    await self._process_batch(batch)
                else:
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f'Pipeline error: {e}')
                await asyncio.sleep(1)

    async def _process_batch(self, batch: list[BufferedLog]):
        now_mono = time.monotonic()
        self._dedup_window = {
            h: t for h, t in self._dedup_window.items() if now_mono - t < self._dedup_ttl
        }

        hot_cutoff = datetime.now(timezone.utc) - timedelta(hours=HOT_THRESHOLD_HOURS)
        hot_rows: list[dict] = []
        warm_rows: list[dict] = []

        for log in batch:
            h = compute_hash(log.source, log.level, log.message)
            if h in self._dedup_window:
                self._deduplicated += 1
                continue
            self._dedup_window[h] = now_mono

            row = {
                'timestamp': log.timestamp,
                'source': log.source,
                'level': log.level,
                'message': log.message,
                'metadata_str': json.dumps(log.metadata) if log.metadata else '{}',
                'metadata': log.metadata,
                'ingestion_time': datetime.fromtimestamp(log.received_at, tz=timezone.utc),
                'hash': h,
            }

            ts = log.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            if ts >= hot_cutoff:
                hot_rows.append(row)
            else:
                warm_rows.append(row)

            self._latencies.append(time.monotonic() - log.received_at)

        loop = asyncio.get_event_loop()

        backoff = 1
        for attempt in range(3):
            try:
                if hot_rows:
                    await loop.run_in_executor(None, self._hot.insert_batch, hot_rows)
                break
            except Exception as e:
                logger.warning(f'ClickHouse insert attempt {attempt + 1} failed: {e}')
                await asyncio.sleep(backoff)
                backoff *= 2

        backoff = 1
        for attempt in range(3):
            try:
                if warm_rows:
                    await loop.run_in_executor(None, self._warm.insert_batch, warm_rows)
                break
            except Exception as e:
                logger.warning(f'PostgreSQL insert attempt {attempt + 1} failed: {e}')
                await asyncio.sleep(backoff)
                backoff *= 2

        self._processed += len(batch)

        if len(self._latencies) > 10000:
            self._latencies = self._latencies[-5000:]

    def percentile(self, p: float) -> float:
        if not self._latencies:
            return 0.0
        sorted_lats = sorted(self._latencies)
        idx = min(int(len(sorted_lats) * p / 100), len(sorted_lats) - 1)
        return round(sorted_lats[idx] * 1000, 2)

    @property
    def stats(self) -> dict:
        total = self._processed + self._deduplicated
        return {
            'processed': self._processed,
            'deduplicated': self._deduplicated,
            'dedup_rate_pct': round(self._deduplicated / max(total, 1) * 100, 2),
            'p50_latency_ms': self.percentile(50),
            'p95_latency_ms': self.percentile(95),
            'p99_latency_ms': self.percentile(99),
        }
