import json
import logging
import psycopg2
import psycopg2.extras
from datetime import datetime

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS logs_warm (
    id BIGSERIAL,
    timestamp TIMESTAMPTZ NOT NULL,
    source VARCHAR(50) NOT NULL,
    level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    metadata JSONB,
    ingestion_time TIMESTAMPTZ,
    hash BIGINT,
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

CREATE TABLE IF NOT EXISTS logs_warm_default PARTITION OF logs_warm DEFAULT;
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_logs_warm_source_ts ON logs_warm (source, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_logs_warm_level_source ON logs_warm (level, source);
CREATE INDEX IF NOT EXISTS idx_logs_warm_hash ON logs_warm (hash);
"""


class PostgresStore:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn = None

    def connect(self):
        self._conn = psycopg2.connect(self._dsn)
        self._conn.autocommit = False
        with self._conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
            cur.execute(CREATE_INDEX_SQL)
        self._conn.commit()
        logger.info('PostgreSQL connected and schema initialized')

    def _ensure_connection(self):
        try:
            if self._conn is None or self._conn.closed:
                self.connect()
            self._conn.isolation_level
        except psycopg2.OperationalError:
            self.connect()

    def insert_batch(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        self._ensure_connection()
        data = []
        for row in rows:
            meta = row.get('metadata')
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            elif row.get('metadata_str'):
                try:
                    meta = json.loads(row['metadata_str'])
                except Exception:
                    meta = {}
            data.append((
                row['timestamp'],
                row['source'],
                row['level'],
                row['message'],
                json.dumps(meta) if meta else None,
                row.get('ingestion_time'),
                row.get('hash'),
            ))
        with self._conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO logs_warm (timestamp, source, level, message, metadata, ingestion_time, hash)
                VALUES %s
                ON CONFLICT DO NOTHING
                """,
                data,
            )
        self._conn.commit()
        return len(data)

    def query_logs(self, source=None, level=None, start_time=None, end_time=None, limit=100) -> list[dict]:
        self._ensure_connection()
        conditions = []
        params = []
        if source:
            conditions.append('source = %s')
            params.append(source)
        if level:
            conditions.append('level = %s')
            params.append(level)
        if start_time:
            conditions.append('timestamp >= %s')
            params.append(start_time)
        if end_time:
            conditions.append('timestamp <= %s')
            params.append(end_time)
        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
        params.append(limit)
        sql = f'SELECT timestamp, source, level, message, metadata FROM logs_warm {where} ORDER BY timestamp DESC LIMIT %s'
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def query_aggregation(self, group_by: list[str], start_time=None, end_time=None) -> list[dict]:
        self._ensure_connection()
        group_cols = ', '.join(group_by)
        conditions = []
        params = []
        if start_time:
            conditions.append('timestamp >= %s')
            params.append(start_time)
        if end_time:
            conditions.append('timestamp <= %s')
            params.append(end_time)
        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
        sql = f'SELECT {group_cols}, COUNT(*) as count FROM logs_warm {where} GROUP BY {group_cols} ORDER BY count DESC'
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def query_timeseries(self, group_by: str, granularity: str, start_time=None, end_time=None) -> list[dict]:
        self._ensure_connection()
        trunc = 'hour' if granularity == '1h' else 'day'
        conditions = []
        params = []
        if start_time:
            conditions.append('timestamp >= %s')
            params.append(start_time)
        if end_time:
            conditions.append('timestamp <= %s')
            params.append(end_time)
        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
        sql = f"SELECT date_trunc('{trunc}', timestamp) as ts, {group_by}, COUNT(*) as count FROM logs_warm {where} GROUP BY ts, {group_by} ORDER BY ts"
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def fetch_for_cold_export(self, cutoff: datetime) -> list[dict]:
        self._ensure_connection()
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                'SELECT timestamp, source, level, message, metadata, ingestion_time, hash FROM logs_warm WHERE timestamp < %s',
                (cutoff,),
            )
            return [dict(r) for r in cur.fetchall()]

    def delete_before(self, cutoff: datetime) -> int:
        self._ensure_connection()
        with self._conn.cursor() as cur:
            cur.execute('DELETE FROM logs_warm WHERE timestamp < %s', (cutoff,))
            deleted = cur.rowcount
        self._conn.commit()
        return deleted

    def count(self) -> int:
        self._ensure_connection()
        with self._conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM logs_warm')
            return cur.fetchone()[0]

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
