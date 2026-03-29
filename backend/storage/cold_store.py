import json
import logging
from datetime import datetime, date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

SCHEMA = pa.schema([
    ('timestamp', pa.timestamp('us', tz='UTC')),
    ('source', pa.string()),
    ('level', pa.string()),
    ('message', pa.string()),
    ('metadata', pa.string()),
    ('ingestion_time', pa.timestamp('us', tz='UTC')),
    ('hash', pa.int64()),
])


class ColdStore:
    def __init__(self, base_path: str = './cold_storage'):
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)

    def export_day(self, records: list[dict], day: date) -> str:
        if not records:
            return ''
        partition_path = (
            self._base_path
            / f'year={day.year}'
            / f'month={day.month:02d}'
            / f'day={day.day:02d}'
        )
        partition_path.mkdir(parents=True, exist_ok=True)
        filepath = partition_path / f'logs_{day.strftime("%Y%m%d")}.parquet'

        timestamps, sources, levels, messages, metadatas, ingestion_times, hashes = [], [], [], [], [], [], []

        for r in records:
            ts = r['timestamp']
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            it = r.get('ingestion_time')
            if isinstance(it, str):
                it = datetime.fromisoformat(it)

            timestamps.append(ts)
            sources.append(r['source'])
            levels.append(r['level'])
            messages.append(r['message'])

            meta = r.get('metadata')
            if meta is None:
                metadatas.append('{}')
            elif isinstance(meta, str):
                metadatas.append(meta)
            else:
                metadatas.append(json.dumps(meta))

            ingestion_times.append(it)
            hashes.append(int(r.get('hash') or 0))

        table = pa.table(
            {
                'timestamp': pa.array(timestamps, type=pa.timestamp('us', tz='UTC')),
                'source': pa.array(sources),
                'level': pa.array(levels),
                'message': pa.array(messages),
                'metadata': pa.array(metadatas),
                'ingestion_time': pa.array(ingestion_times, type=pa.timestamp('us', tz='UTC')),
                'hash': pa.array(hashes, type=pa.int64()),
            },
            schema=SCHEMA,
        )

        pq.write_table(table, filepath, compression='snappy')
        size_mb = filepath.stat().st_size / (1024 * 1024)
        logger.info(f'Cold export: {filepath} ({len(records)} rows, {size_mb:.2f} MB)')
        return str(filepath)

    def size_gb(self) -> float:
        total = sum(f.stat().st_size for f in self._base_path.rglob('*.parquet'))
        return total / (1024 ** 3)

    def list_files(self) -> list[str]:
        return [str(f) for f in sorted(self._base_path.rglob('*.parquet'))]
