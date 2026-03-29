import logging
import os
from datetime import datetime
from clickhouse_driver import Client

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS logs_hot (
    timestamp DateTime,
    source String,
    level String,
    message String,
    metadata String,
    ingestion_time DateTime,
    hash UInt64
) ENGINE = MergeTree()
ORDER BY (source, level, timestamp)
PARTITION BY toDate(timestamp)
"""


class ClickHouseStore:
    def __init__(self, host: str, port: int = 9000, database: str = 'default'):
        self._host = host
        self._port = port
        self._database = database
        self._client: Client = None

    def connect(self):
        password = os.getenv('CLICKHOUSE_PASSWORD', '')
        self._client = Client(host=self._host, port=self._port, database=self._database, password=password)
        self._client.execute(CREATE_TABLE_SQL)
        logger.info('ClickHouse connected and schema initialized')

    def insert_batch(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        data = [
            (
                row['timestamp'],
                row['source'],
                row['level'],
                row['message'],
                row.get('metadata_str', '{}'),
                row['ingestion_time'],
                row['hash'],
            )
            for row in rows
        ]
        self._client.execute(
            'INSERT INTO logs_hot (timestamp, source, level, message, metadata, ingestion_time, hash) VALUES',
            data,
        )
        return len(data)

    def query_logs(
        self,
        source=None,
        level=None,
        start_time=None,
        end_time=None,
        limit=100,
    ) -> list[dict]:
        conditions = []
        params = {}
        if source:
            conditions.append('source = %(source)s')
            params['source'] = source
        if level:
            conditions.append('level = %(level)s')
            params['level'] = level
        if start_time:
            conditions.append('timestamp >= %(start_time)s')
            params['start_time'] = start_time
        if end_time:
            conditions.append('timestamp <= %(end_time)s')
            params['end_time'] = end_time
        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
        params['limit'] = limit
        sql = f'SELECT timestamp, source, level, message, metadata FROM logs_hot {where} ORDER BY timestamp DESC LIMIT %(limit)s'
        rows = self._client.execute(sql, params)
        return [
            {'timestamp': r[0], 'source': r[1], 'level': r[2], 'message': r[3], 'metadata': r[4]}
            for r in rows
        ]

    def query_aggregation(self, group_by: list[str], start_time=None, end_time=None) -> list[dict]:
        group_cols = ', '.join(group_by)
        conditions = []
        params = {}
        if start_time:
            conditions.append('timestamp >= %(start_time)s')
            params['start_time'] = start_time
        if end_time:
            conditions.append('timestamp <= %(end_time)s')
            params['end_time'] = end_time
        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
        sql = f'SELECT {group_cols}, count(*) as count FROM logs_hot {where} GROUP BY {group_cols} ORDER BY count DESC'
        rows = self._client.execute(sql, params)
        return [dict(zip(group_by + ['count'], r)) for r in rows]

    def query_timeseries(self, group_by: str, granularity: str, start_time=None, end_time=None) -> list[dict]:
        trunc_fn = 'toStartOfHour' if granularity == '1h' else 'toStartOfDay'
        conditions = []
        params = {}
        if start_time:
            conditions.append('timestamp >= %(start_time)s')
            params['start_time'] = start_time
        if end_time:
            conditions.append('timestamp <= %(end_time)s')
            params['end_time'] = end_time
        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
        sql = f'SELECT {trunc_fn}(timestamp) as ts, {group_by}, count(*) as count FROM logs_hot {where} GROUP BY ts, {group_by} ORDER BY ts'
        rows = self._client.execute(sql, params)
        return [{'timestamp': r[0], group_by: r[1], 'count': r[2]} for r in rows]

    def move_to_warm_cutoff(self, cutoff: datetime) -> list[dict]:
        rows = self._client.execute(
            'SELECT timestamp, source, level, message, metadata, ingestion_time, hash FROM logs_hot WHERE timestamp < %(cutoff)s',
            {'cutoff': cutoff},
        )
        result = [
            {
                'timestamp': r[0],
                'source': r[1],
                'level': r[2],
                'message': r[3],
                'metadata_str': r[4],
                'ingestion_time': r[5],
                'hash': r[6],
            }
            for r in rows
        ]
        if result:
            self._client.execute(
                'ALTER TABLE logs_hot DELETE WHERE timestamp < %(cutoff)s',
                {'cutoff': cutoff},
            )
        return result

    def count(self) -> int:
        result = self._client.execute('SELECT count(*) FROM logs_hot')
        return result[0][0]

    def close(self):
        if self._client:
            self._client.disconnect()
