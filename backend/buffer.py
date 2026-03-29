import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class BufferedLog:
    timestamp: datetime
    source: str
    level: str
    message: str
    metadata: Optional[dict]
    received_at: float


class IngestBuffer:
    def __init__(self, max_size: int = 10000):
        self._buffer: deque = deque()
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._total_received = 0
        self._total_dropped = 0

    async def push(self, log: BufferedLog) -> bool:
        async with self._lock:
            if len(self._buffer) >= self._max_size:
                self._total_dropped += 1
                return False
            self._buffer.append(log)
            self._total_received += 1
            return True

    async def drain(self, batch_size: int = 1000) -> list[BufferedLog]:
        async with self._lock:
            batch = []
            while self._buffer and len(batch) < batch_size:
                batch.append(self._buffer.popleft())
            return batch

    @property
    def size(self) -> int:
        return len(self._buffer)

    @property
    def utilization(self) -> float:
        return len(self._buffer) / self._max_size

    @property
    def stats(self) -> dict:
        return {
            'buffer_size': len(self._buffer),
            'total_received': self._total_received,
            'total_dropped': self._total_dropped,
            'utilization_pct': round(self.utilization * 100, 2),
        }
