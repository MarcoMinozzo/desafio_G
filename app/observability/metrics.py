"""In-memory quality counters and the alerts that fire when the series worsens.

The snapshot has counts, corpus age, and alert names. It has no user id and no
tool value. The map is empty after a process restart.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.domain.models import MetricsSnapshot

logger = logging.getLogger("getnet.assist.metrics")

MIN_SAMPLE = 10
HALLUCINATED_RATIO = 0.3
HANDOFF_RATIO = 0.5
CORPUS_MAX_AGE_DAYS = 30


class MetricsStore:
    def __init__(self, *, corpus_age_days: int = 0) -> None:
        self.corpus_age_days = max(0, corpus_age_days)
        self.requests = 0
        self.answered = 0
        self.refused = 0
        self.handoffs = 0
        self.verified = 0
        self.hallucinated = 0
        self.unverified = 0
        self._emitted: set[str] = set()
        self._emit(self.alerts())

    def record(self, *, outcome: str, verdict: str) -> None:
        self.requests += 1
        if outcome == "answered":
            self.answered += 1
        elif outcome == "refused":
            self.refused += 1
        elif outcome == "handoff":
            self.handoffs += 1
        if verdict == "verified":
            self.verified += 1
        elif verdict == "hallucinated":
            self.hallucinated += 1
        elif verdict == "unverified":
            self.unverified += 1
        self._emit(self.alerts())

    def alerts(self) -> list[str]:
        found: list[str] = []
        if self.corpus_age_days >= CORPUS_MAX_AGE_DAYS:
            found.append("corpus_stale")
        if self.requests >= MIN_SAMPLE:
            if self.hallucinated / self.requests > HALLUCINATED_RATIO:
                found.append("hallucinated_ratio")
            if self.handoffs / self.requests > HANDOFF_RATIO:
                found.append("handoff_ratio")
        return found

    def snapshot(self) -> MetricsSnapshot:
        return MetricsSnapshot(
            requests=self.requests,
            answered=self.answered,
            refused=self.refused,
            handoffs=self.handoffs,
            verified=self.verified,
            hallucinated=self.hallucinated,
            unverified=self.unverified,
            corpus_age_days=self.corpus_age_days,
            corpus_stale=self.corpus_age_days >= CORPUS_MAX_AGE_DAYS,
            alerts=self.alerts(),
        )

    def _emit(self, names: list[str]) -> None:
        for name in names:
            if name in self._emitted:
                continue
            self._emitted.add(name)
            logger.warning(
                json.dumps(
                    {
                        "alert": name,
                        "requests": self.requests,
                        "corpus_age_days": self.corpus_age_days,
                    }
                )
            )


def corpus_age_days(corpus_dir: Path, *, now: datetime | None = None) -> int:
    files = [path for path in corpus_dir.glob("*.md") if path.is_file()]
    if not files:
        return 0
    oldest = min(path.stat().st_mtime for path in files)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return max(0, int((current.timestamp() - oldest) // 86400))
