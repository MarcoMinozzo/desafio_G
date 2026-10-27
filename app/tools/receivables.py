"""Read receivables for the request user_id only."""

from __future__ import annotations

from typing import Any

from app.tools.store import merchant_for


def get_receivables(merchants: dict[str, Any], user_id: str) -> dict[str, Any]:
    record = merchant_for(merchants, user_id)
    if record is None:
        return {"status": "not_found", "user_id": user_id}
    receivable = record["receivable"]
    return {
        "status": receivable["status"],
        "user_id": user_id,
        "sales_label": receivable["sales_label"],
        "amount_brl": receivable["amount_brl"],
        "expected_deposit": receivable["expected_deposit"],
    }
