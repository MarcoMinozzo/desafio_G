"""Process-local conversation memory. The key is the caller user_id plus the session id.

Turns keep the merchant's own words, the intent, and the detail. They do not
keep tool values, amounts, or another user's history. A session id presented
by a different user_id does not open the original thread.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryTurn:
    message: str
    intent: str
    detail: str
    topic: str


class SessionStore:
    def __init__(self, limit: int = 4) -> None:
        self._items: dict[tuple[str, str], list[MemoryTurn]] = {}
        self._limit = limit

    def latest(self, user_id: str, session_id: str) -> MemoryTurn | None:
        turns = self._items.get((user_id, session_id))
        if not turns:
            return None
        return turns[-1]

    def remember(self, user_id: str, session_id: str, turn: MemoryTurn) -> None:
        key = (user_id, session_id)
        turns = self._items.setdefault(key, [])
        turns.append(turn)
        if len(turns) > self._limit:
            del turns[: len(turns) - self._limit]
