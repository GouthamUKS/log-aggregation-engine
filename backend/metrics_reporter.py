import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from buffer import IngestBuffer
from pipeline import ProcessingPipeline
from storage.clickhouse_store import ClickHouseStore
from storage.postgres_store import PostgresStore
from storage.cold_store import ColdStore

logger = logging.getLogger(__name__)


class MetricsReporter:
    def __init__(
        self,
        buffer: IngestBuffer,
        pipeline: ProcessingPipeline,
        hot: ClickHouseStore,
        warm: PostgresStore,
        cold: ColdStore,
        interval: int = 60,
    ):
        self._buffer = buffer
        self._pipeline = pipeline
        self._hot = hot
        self._warm = warm
        self._cold = cold
        self._interval = interval
        self._running = False
        self._task = None
        self._last_processed = 0
        self._last_ts = time.monotonic()

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self):
        while self._running:
            await asyncio.sleep(self._interval)
            if self._running:
                await self._report()

    async def _report(self):
        now = time.monotonic()
        elapsed = now - self._last_ts
        pipeline_stats = self._pipeline.stats
        current = pipeline_stats['processed']
        rate = (current - self._last_processed) / max(elapsed, 1)
        self._last_processed = current
        self._last_ts = now

        loop = asyncio.get_event_loop()

        try:
            hot_count = await loop.run_in_executor(None, self._hot.count)
        except Exception:
            hot_count = -1

        try:
            warm_count = await loop.run_in_executor(None, self._warm.count)
        except Exception:
            warm_count = -1

        cold_gb = self._cold.size_gb()

        metrics = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'ingest_rate_per_sec': round(rate, 1),
            'ingest_p50_latency_ms': pipeline_stats['p50_latency_ms'],
            'ingest_p95_latency_ms': pipeline_stats['p95_latency_ms'],
            'ingest_p99_latency_ms': pipeline_stats['p99_latency_ms'],
            'buffer_size': self._buffer.size,
            'buffer_utilization_pct': self._buffer.stats['utilization_pct'],
            'hot_count': hot_count,
            'warm_count': warm_count,
            'cold_size_gb': round(cold_gb, 4),
            'dedup_rate_pct': pipeline_stats['dedup_rate_pct'],
            'dlq_count': self._count_dlq(),
        }
        logger.info(f'METRICS {json.dumps(metrics)}')

    def _count_dlq(self) -> int:
        import os
        dlq_path = os.getenv('DLQ_PATH', './dlq.jsonl')
        try:
            with open(dlq_path) as f:
                return sum(1 for _ in f)
        except FileNotFoundError:
            return 0
