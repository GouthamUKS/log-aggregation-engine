import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from storage.clickhouse_store import ClickHouseStore
from storage.postgres_store import PostgresStore

logger = logging.getLogger(__name__)

HOT_THRESHOLD_HOURS = 24
WARM_THRESHOLD_DAYS = 30


class QueryRouter:
    def __init__(self, hot: ClickHouseStore, warm: PostgresStore):
        self._hot = hot
        self._warm = warm

    def _tiers(self, start_time: Optional[datetime], end_time: Optional[datetime]) -> list[str]:
        now = datetime.now(timezone.utc)
        hot_boundary = now - timedelta(hours=HOT_THRESHOLD_HOURS)

        end = end_time or now
        start = start_time or (now - timedelta(days=WARM_THRESHOLD_DAYS))

        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

        tiers = []
        if end >= hot_boundary:
            tiers.append('hot')
        if start < hot_boundary:
            tiers.append('warm')
        return tiers or ['hot']

    def query_logs(
        self,
        source=None,
        level=None,
        start_time=None,
        end_time=None,
        limit=100,
    ) -> list[dict]:
        tiers = self._tiers(start_time, end_time)
        results = []

        if 'hot' in tiers:
            results.extend(self._hot.query_logs(source, level, start_time, end_time, limit))
        if 'warm' in tiers:
            results.extend(self._warm.query_logs(source, level, start_time, end_time, limit))

        results.sort(key=lambda x: x['timestamp'], reverse=True)
        return results[:limit]

    def query_aggregation(self, group_by: list[str], start_time=None, end_time=None) -> list[dict]:
        tiers = self._tiers(start_time, end_time)
        combined: dict[tuple, int] = {}

        if 'hot' in tiers:
            for row in self._hot.query_aggregation(group_by, start_time, end_time):
                key = tuple(row.get(g, '') for g in group_by)
                combined[key] = combined.get(key, 0) + row['count']

        if 'warm' in tiers:
            for row in self._warm.query_aggregation(group_by, start_time, end_time):
                key = tuple(row.get(g, '') for g in group_by)
                combined[key] = combined.get(key, 0) + row['count']

        result = []
        for key, count in sorted(combined.items(), key=lambda x: -x[1]):
            row = dict(zip(group_by, key))
            row['count'] = count
            result.append(row)
        return result

    def query_timeseries(self, group_by: str, granularity: str, start_time=None, end_time=None) -> list[dict]:
        tiers = self._tiers(start_time, end_time)
        combined: dict[tuple, int] = {}

        if 'hot' in tiers:
            for row in self._hot.query_timeseries(group_by, granularity, start_time, end_time):
                key = (row['timestamp'], row.get(group_by, ''))
                combined[key] = combined.get(key, 0) + row['count']

        if 'warm' in tiers:
            for row in self._warm.query_timeseries(group_by, granularity, start_time, end_time):
                key = (row['timestamp'], row.get(group_by, ''))
                combined[key] = combined.get(key, 0) + row['count']

        return [
            {'timestamp': k[0], group_by: k[1], 'count': v}
            for k, v in sorted(combined.items())
        ]
