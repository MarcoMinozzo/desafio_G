"""Merchant fixture shared by the support tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_merchants(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("merchants file must be an object keyed by user_id")
    return payload


def merchant_for(merchants: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    record = merchants.get(user_id)
    return record if isinstance(record, dict) else None
