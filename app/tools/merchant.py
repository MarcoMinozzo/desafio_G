"""Read the merchant profile for the request user_id only."""

from __future__ import annotations

from typing import Any

from app.tools.store import merchant_for


def get_merchant_account(merchants: dict[str, Any], user_id: str) -> dict[str, Any]:
    record = merchant_for(merchants, user_id)
    if record is None:
        return {"status": "not_found", "user_id": user_id}
    return {
        "status": "found",
        "user_id": user_id,
        "machine_model": record["machine_model"],
        "pix_enabled": record["pix_enabled"],
        "receiving_setup": record["receiving_setup"],
    }
