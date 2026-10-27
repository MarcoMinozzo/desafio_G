"""Diagnose the request user's card machine. Symptom is connectivity or decline."""

from __future__ import annotations

from typing import Any

from app.tools.store import merchant_for


def diagnose_terminal(merchants: dict[str, Any], user_id: str, symptom: str) -> dict[str, Any]:
    if symptom not in {"connectivity", "decline"}:
        raise ValueError("symptom must be connectivity or decline")
    record = merchant_for(merchants, user_id)
    if record is None:
        return {"status": "not_found", "user_id": user_id, "symptom": symptom, "steps": []}
    terminal = record["terminal"]
    steps_key = "connectivity_steps" if symptom == "connectivity" else "decline_steps"
    return {
        "status": "found",
        "user_id": user_id,
        "symptom": symptom,
        "machine_model": record["machine_model"],
        "steps": list(terminal[steps_key]),
    }
