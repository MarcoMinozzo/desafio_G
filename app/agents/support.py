"""Account support. Every tool call uses the request user_id, never an id from the text."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.models import ClaimedStatement
from app.observability.hallucination_check import StatedField
from app.orchestration.handoff import Handoff
from app.tools.merchant import get_merchant_account
from app.tools.receivables import get_receivables
from app.tools.terminal import diagnose_terminal


@dataclass
class SupportResult:
    answer: str
    confidence: float
    tools: list[str] = field(default_factory=list)
    claims: list[ClaimedStatement] = field(default_factory=list)
    stated: list[StatedField] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)


class SupportAgent:
    def __init__(self, merchants: dict[str, Any]) -> None:
        self._merchants = merchants

    def answer(self, handoff: Handoff) -> SupportResult:
        user_id = str(handoff.payload.get("user_id", ""))
        detail = str(handoff.payload.get("detail", "receivables"))
        if detail == "decline":
            return self._terminal(user_id, "decline")
        if detail == "connectivity":
            return self._terminal(user_id, "connectivity")
        if detail == "profile":
            return self._profile(user_id)
        return self._receivables(user_id)

    def _receivables(self, user_id: str) -> SupportResult:
        record = get_receivables(self._merchants, user_id)
        if record["status"] == "not_found":
            return self._result(
                answer=(
                    "No receivables record was found for this user. "
                    "I will not guess a balance or a deposit date."
                ),
                confidence=0.7,
                tool="get_receivables",
                record=record,
                names=["status"],
            )
        amount = record["amount_brl"]
        return self._result(
            answer=(
                f"Yesterday's sales of BRL {amount:.2f} for your account are "
                f"{record['status']} for deposit on {record['expected_deposit']}."
            ),
            confidence=0.9,
            tool="get_receivables",
            record=record,
            names=["status", "amount_brl", "expected_deposit"],
        )

    def _profile(self, user_id: str) -> SupportResult:
        record = get_merchant_account(self._merchants, user_id)
        if record["status"] == "not_found":
            return self._result(
                answer="No merchant profile was found for this user.",
                confidence=0.7,
                tool="get_merchant_account",
                record=record,
                names=["status"],
            )
        pix = "enabled" if record["pix_enabled"] else "not enabled"
        return self._result(
            answer=(
                f"Your {record['machine_model']} has Pix {pix}. "
                f"Receiving setup: {record['receiving_setup']}."
            ),
            confidence=0.9,
            tool="get_merchant_account",
            record=record,
            names=["machine_model", "pix_enabled", "receiving_setup"],
        )

    def _terminal(self, user_id: str, symptom: str) -> SupportResult:
        record = diagnose_terminal(self._merchants, user_id, symptom)
        if record["status"] == "not_found":
            return self._result(
                answer=(
                    "No card machine record was found for this user. "
                    "I will not guess the terminal state."
                ),
                confidence=0.7,
                tool="diagnose_terminal",
                record=record,
                names=["status"],
            )
        steps = " ".join(f"{index}. {step}" for index, step in enumerate(record["steps"], start=1))
        label = "connectivity" if symptom == "connectivity" else "decline"
        return self._result(
            answer=(
                f"For your {record['machine_model']}, these are the {label} steps on file: {steps}"
            ),
            confidence=0.86,
            tool="diagnose_terminal",
            record=record,
            names=["machine_model", "symptom", "steps"],
        )

    def _result(
        self,
        *,
        answer: str,
        confidence: float,
        tool: str,
        record: dict[str, Any],
        names: list[str],
    ) -> SupportResult:
        claims = [
            ClaimedStatement(kind="support", citations=[tool], fields=[name])
            for name in names
        ]
        stated = [StatedField(tool=tool, field=name, value=record[name]) for name in names]
        return SupportResult(
            answer=answer,
            confidence=confidence,
            tools=[tool],
            claims=claims,
            stated=stated,
            payload=record,
        )
