"""In-memory review records and one JSON log line per chat."""

from __future__ import annotations

import json
import logging

from app.domain.models import ReviewRecord

logger = logging.getLogger("getnet.assist")


class TraceStore:
    def __init__(self) -> None:
        self._items: dict[str, ReviewRecord] = {}

    def put(self, record: ReviewRecord) -> None:
        self._items[record.trace_id] = record
        logger.info(json.dumps(record.model_dump(), ensure_ascii=False))

    def get(self, trace_id: str) -> ReviewRecord | None:
        return self._items.get(trace_id)
