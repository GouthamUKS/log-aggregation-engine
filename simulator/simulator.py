import asyncio
import json
import logging
import os
import random
import time
from datetime import datetime, timezone

import httpx

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:8000/logs')
BATCH_SIZE = 100
TICK_INTERVAL = 0.01

SOURCES = {
    'api-service': {
        'rate': 3000,
        'levels': ['INFO', 'INFO', 'INFO', 'WARN', 'ERROR'],
        'messages': [
            'Request to /users took {ms}ms',
            'Request to /orders took {ms}ms',
            'Request to /products took {ms}ms',
            'Database connection timeout after {ms}ms',
            'Cache miss for key user:{id}',
            'Authentication failed for token {id}',
            'Rate limit exceeded for client {id}',
        ],
    },
    'worker-service': {
        'rate': 2000,
        'levels': ['INFO', 'INFO', 'ERROR'],
        'messages': [
            'Job {id} started processing',
            'Job {id} completed in {ms}ms',
            'Job {id} failed: connection timeout',
            'Queue depth: {n} pending jobs',
            'Worker heartbeat OK',
        ],
    },
    'cache-service': {
        'rate': 2500,
        'levels': ['INFO', 'INFO', 'WARN'],
        'messages': [
            'Cache hit ratio: {pct}%',
            'Evicted {n} keys due to memory pressure',
            'Memory usage at {pct}%',
            'Key {id} expired',
            'Cluster replication lag: {ms}ms',
        ],
    },
    'auth-service': {
        'rate': 1000,
        'levels': ['INFO', 'WARN', 'ERROR'],
        'messages': [
            'Login attempt for user:{id}',
            'Token validated for user:{id}',
            'Invalid token: {id}',
            'Password reset requested for user:{id}',
            'MFA verification failed for user:{id}',
        ],
    },
    'db-service': {
        'rate': 500,
        'levels': ['INFO', 'WARN', 'ERROR'],
        'messages': [
            'Query executed in {ms}ms',
            'Slow query detected: {ms}ms on table orders',
            'Connection pool exhausted ({n} waiting)',
            'Replication lag: {ms}ms',
            'Vacuum completed on table logs',
        ],
    },
}

_sources = list(SOURCES.items())
_weights = [cfg['rate'] for _, cfg in _sources]
_total_rate = sum(_weights)


def make_log(source: str, cfg: dict, ts: datetime) -> dict:
    template = random.choice(cfg['messages'])
    message = template.format(
        ms=random.randint(1, 9999),
        id=random.randint(10000, 99999),
        pct=random.randint(1, 100),
        n=random.randint(1, 1000),
    )
    return {
        'timestamp': ts.isoformat(),
        'source': source,
        'level': random.choice(cfg['levels']),
        'message': message,
        'metadata': {
            'host': f'{source}-{random.randint(1, 5)}',
            'pid': random.randint(1000, 32767),
            'region': random.choice(['us-west-2', 'us-east-1', 'eu-west-1']),
        },
    }


def peak_multiplier() -> float:
    hour = datetime.now().hour
    if 8 <= hour < 10 or 18 <= hour < 20:
        return 2.0
    return 1.0


async def send_batch(client: httpx.AsyncClient, logs: list[dict]) -> tuple[int, float]:
    start = time.monotonic()
    try:
        resp = await client.post(BACKEND_URL, content=json.dumps({'logs': logs}), headers={'Content-Type': 'application/json'}, timeout=10.0)
        return resp.status_code, time.monotonic() - start
    except Exception as e:
        logger.error(f'Send error: {e}')
        return 0, 0.0


async def run():
    async with httpx.AsyncClient() as client:
        batch: list[dict] = []
        latencies: list[float] = []
        total_sent = 0
        report_at = time.monotonic() + 10
        burst_until = 0.0
        surge_until = 0.0
        tick = 0

        while True:
            now_ts = datetime.now(timezone.utc)
            now_mono = time.monotonic()
            multiplier = peak_multiplier()

            if tick % 600 == 0 and tick > 0:
                burst_until = now_mono + 120

            if tick % 1800 == 0 and tick > 0:
                surge_until = now_mono + 60

            is_burst = now_mono < burst_until
            is_surge = now_mono < surge_until

            effective_rate = _total_rate * multiplier * (1.5 if is_burst else 1.0)
            events_this_tick = int(effective_rate * TICK_INTERVAL)

            for _ in range(events_this_tick):
                source, cfg = random.choices(_sources, weights=_weights, k=1)[0]
                current_cfg = cfg if not is_surge else {**cfg, 'levels': cfg['levels'] + ['ERROR', 'ERROR']}
                log = make_log(source, current_cfg, now_ts)
                batch.append(log)

                if random.random() < 0.02:
                    batch.append(make_log(source, current_cfg, now_ts))
                    batch.append(make_log(source, current_cfg, now_ts))

            while len(batch) >= BATCH_SIZE:
                payload = batch[:BATCH_SIZE]
                batch = batch[BATCH_SIZE:]
                status, latency = await send_batch(client, payload)
                if latency > 0:
                    latencies.append(latency * 1000)
                    total_sent += len(payload)

            if now_mono >= report_at:
                if latencies:
                    latencies.sort()
                    p50 = latencies[int(len(latencies) * 0.50)]
                    p95 = latencies[int(len(latencies) * 0.95)]
                    p99 = latencies[int(len(latencies) * 0.99)]
                    logger.info(
                        f'sent={total_sent} rate={int(len(latencies) / 10)}/s '
                        f'p50={p50:.1f}ms p95={p95:.1f}ms p99={p99:.1f}ms '
                        f'backlog={len(batch)} burst={is_burst} surge={is_surge}'
                    )
                    latencies = []
                report_at = now_mono + 10

            tick += 1
            await asyncio.sleep(TICK_INTERVAL)


if __name__ == '__main__':
    asyncio.run(run())
