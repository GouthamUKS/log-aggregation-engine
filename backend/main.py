import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from models import LogBatch
from buffer import IngestBuffer, BufferedLog
from pipeline import ProcessingPipeline
from query_router import QueryRouter
from lifecycle import LifecycleManager
from metrics_reporter import MetricsReporter
from storage.clickhouse_store import ClickHouseStore
from storage.postgres_store import PostgresStore
from storage.cold_store import ColdStore

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
)
logger = logging.getLogger(__name__)

DLQ_PATH = Path(os.getenv('DLQ_PATH', './dlq.jsonl'))

hot = ClickHouseStore(
    host=os.getenv('CLICKHOUSE_HOST', 'localhost'),
    port=int(os.getenv('CLICKHOUSE_PORT', '9000')),
)
warm = PostgresStore(dsn=os.getenv('POSTGRES_DSN', 'postgresql://postgres:postgres@localhost:5432/logs'))
cold = ColdStore(base_path=os.getenv('COLD_STORAGE_PATH', './cold_storage'))
buffer = IngestBuffer(max_size=10000)
pipeline = ProcessingPipeline(buffer, hot, warm)
router = QueryRouter(hot, warm)
lifecycle = LifecycleManager(hot, warm, cold)
reporter = MetricsReporter(buffer, pipeline, hot, warm, cold, interval=60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    hot.connect()
    warm.connect()
    await pipeline.start()
    await lifecycle.start()
    await reporter.start()
    yield
    await reporter.stop()
    await lifecycle.stop()
    await pipeline.stop()
    hot.close()
    warm.close()


app = FastAPI(title='Log Aggregation Engine', version='1.0.0', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


def write_dlq(log_data: dict, reason: str):
    with DLQ_PATH.open('a') as f:
        f.write(json.dumps({
            'log': log_data,
            'reason': reason,
            'ts': datetime.now(timezone.utc).isoformat(),
        }) + '\n')


@app.post('/logs', status_code=202)
async def ingest_logs(batch: LogBatch):
    if buffer.utilization >= 0.9:
        raise HTTPException(status_code=429, detail='Buffer at capacity, retry later')

    accepted = 0
    rejected = 0

    for log in batch.logs:
        buffered = BufferedLog(
            timestamp=log.timestamp,
            source=log.source,
            level=log.level,
            message=log.message,
            metadata=log.metadata,
            received_at=time.monotonic(),
        )
        pushed = await buffer.push(buffered)
        if pushed:
            accepted += 1
        else:
            write_dlq(log.model_dump(mode='json'), 'buffer_full')
            rejected += 1

    return {'accepted': accepted, 'rejected': rejected}


@app.get('/query/logs')
def query_logs(
    source: Optional[str] = None,
    level: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = Query(default=100, ge=1, le=10000),
):
    return router.query_logs(source, level, start_time, end_time, limit)


@app.get('/query/aggregation')
def query_aggregation(
    metric: str = 'count',
    group_by: str = 'source',
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
):
    group_cols = [c.strip() for c in group_by.split(',') if c.strip()]
    if not group_cols:
        raise HTTPException(status_code=400, detail='group_by cannot be empty')
    return router.query_aggregation(group_cols, start_time, end_time)


@app.get('/query/timeseries')
def query_timeseries(
    metric: str = 'count',
    group_by: str = 'source',
    granularity: str = '1h',
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
):
    if granularity not in ('1h', '1d'):
        raise HTTPException(status_code=400, detail='granularity must be 1h or 1d')
    return router.query_timeseries(group_by.strip(), granularity, start_time, end_time)


@app.get('/health')
def health():
    try:
        hot_count = hot.count()
    except Exception:
        hot_count = -1
    try:
        warm_count = warm.count()
    except Exception:
        warm_count = -1

    return {
        'status': 'ok',
        'hot_count': hot_count,
        'warm_count': warm_count,
        'cold_files': len(cold.list_files()),
        'cold_size_gb': round(cold.size_gb(), 4),
        'buffer': buffer.stats,
        'pipeline': pipeline.stats,
    }
