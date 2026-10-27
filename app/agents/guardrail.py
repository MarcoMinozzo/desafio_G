"""Refuse empty messages, instruction override, and cross-customer reads."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.orchestration.handoff import Handoff

_INJECTION = (
    "ignore previous",
    "ignore all instructions",
    "ignore your instructions",
    "system prompt",
    "reveal your prompt",
    "reveal the prompt",
    "jailbreak",
    "disregard the rules",
    "you are now",
)
_OTHER_CUSTOMER = (
    "another customer",
    "other customer",
    "other merchant",
)
_USER_ID = re.compile(r"\bcliente[0-9]+\b", re.IGNORECASE)


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    reason: str


class GuardrailAgent:
    def review(self, handoff: Handoff) -> GuardrailDecision:
        message = str(handoff.payload.get("message", ""))
        user_id = str(handoff.payload.get("user_id", ""))
        if not message.strip():
            return GuardrailDecision(False, "empty")
        lowered = message.lower()
        if any(pattern in lowered for pattern in _INJECTION):
            return GuardrailDecision(False, "injection")
        if any(pattern in lowered for pattern in _OTHER_CUSTOMER):
            return GuardrailDecision(False, "cross_customer")
        for found in _USER_ID.findall(message):
            if found.lower() != user_id.lower():
                return GuardrailDecision(False, "cross_customer")
        return GuardrailDecision(True, "allowed")
