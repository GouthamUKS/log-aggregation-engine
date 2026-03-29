from pydantic import BaseModel, field_validator
from typing import Optional, Any
from datetime import datetime


class LogEvent(BaseModel):
    timestamp: datetime
    source: str
    level: str
    message: str
    metadata: Optional[dict[str, Any]] = None

    @field_validator('level')
    @classmethod
    def validate_level(cls, v):
        if v not in ('DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL'):
            raise ValueError(f'invalid log level: {v}')
        return v

    @field_validator('source')
    @classmethod
    def validate_source(cls, v):
        if not v or len(v) > 50:
            raise ValueError('source must be 1-50 characters')
        return v


class LogBatch(BaseModel):
    logs: list[LogEvent]
