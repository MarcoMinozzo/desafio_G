"""Open a human handoff when the assistant should not guess."""

from __future__ import annotations

import secrets

from app.domain.models import Handoff as HandoffReceipt
from app.domain.models import HandoffReason


class EscalationAgent:
    def open(self, reason: HandoffReason) -> HandoffReceipt:
        reference = "ESC-" + secrets.token_hex(4).upper()
        return HandoffReceipt(reference=reference, reason=reason)
