"""In-process handoff passed from one agent to the next."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Handoff:
    trace_id: str
    intent: str
    confidence: float
    payload: dict[str, Any] = field(default_factory=dict)
