import asyncio
import logging
from datetime import datetime, timezone, timedelta

from storage.clickhouse_store import ClickHouseStore
from storage.postgres_store import PostgresStore
from storage.cold_store import ColdStore

logger = logging.getLogger(__name__)


class LifecycleManager:
    def __init__(self, hot: ClickHouseStore, warm: PostgresStore, cold: ColdStore):
        self._hot = hot
        self._warm = warm
        self._cold = cold
        self._running = False
        self._task = None

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._schedule_loop())
        logger.info('Lifecycle manager started')

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _schedule_loop(self):
        while self._running:
            now = datetime.now(timezone.utc)
            next_2am = now.replace(hour=2, minute=0, second=0, microsecond=0)
            if now >= next_2am:
                next_2am += timedelta(days=1)
            sleep_secs = (next_2am - now).total_seconds()
            await asyncio.sleep(sleep_secs)
            if self._running:
                await self.hot_to_warm()

            now = datetime.now(timezone.utc)
            next_3am = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if now >= next_3am:
                next_3am += timedelta(days=1)
            sleep_secs = (next_3am - now).total_seconds()
            await asyncio.sleep(sleep_secs)
            if self._running:
                await self.warm_to_cold()

    async def hot_to_warm(self):
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        logger.info(f'hot->warm migration starting: cutoff={cutoff.isoformat()}')
        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(None, self._hot.move_to_warm_cutoff, cutoff)
        if rows:
            await loop.run_in_executor(None, self._warm.insert_batch, rows)
            logger.info(f'hot->warm: migrated {len(rows)} rows')
        else:
            logger.info('hot->warm: no rows eligible for migration')

    async def warm_to_cold(self):
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        target_date = (cutoff - timedelta(days=1)).date()
        logger.info(f'warm->cold migration starting: cutoff={cutoff.isoformat()}, date={target_date}')
        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(None, self._warm.fetch_for_cold_export, cutoff)
        if rows:
            path = await loop.run_in_executor(None, self._cold.export_day, rows, target_date)
            deleted = await loop.run_in_executor(None, self._warm.delete_before, cutoff)
            logger.info(f'warm->cold: exported {len(rows)} rows to {path}, deleted {deleted} from warm')
        else:
            logger.info('warm->cold: no rows eligible for export')
