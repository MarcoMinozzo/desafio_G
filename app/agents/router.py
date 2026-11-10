"""Intent table with an optional structured-model override."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from app.llm.client import LLMClient
from app.orchestration.handoff import Handoff

ALLOWED = {
    "product_knowledge",
    "account_support",
    "general_web",
    "human_handoff",
    "out_of_scope",
}


_CONTINUABLE = {"product_knowledge", "account_support", "general_web"}
_PRODUCT_WORDS = (
    "classica",
    "get smart",
    "smart",
    "pix",
    "bank account",
    "antecip",
    "crediario",
    "installment",
    "whatsapp",
    "payment link",
)


@dataclass(frozen=True)
class RouteDecision:
    intent: str
    detail: str
    confidence: float
    sequence: tuple[str, ...] = ()
    continued: bool = False

    def steps(self) -> tuple[str, ...]:
        if self.sequence:
            return self.sequence
        return (self.intent,)


class RouterAgent:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def route(self, handoff: Handoff) -> RouteDecision:
        message = str(handoff.payload.get("message", ""))
        table = _table(message)
        if len(table.steps()) > 1:
            return table
        model_intent = self._llm.classify(message)
        if model_intent in ALLOWED:
            return RouteDecision(model_intent, _detail(message, model_intent), 0.8)
        continued = _continue(handoff) if table.intent == "out_of_scope" else None
        if continued is not None:
            return continued
        return table


def _table(message: str) -> RouteDecision:
    text = _fold(message)
    if _contains(text, ("talk to a human", "talk to a person", "speak to a person", "human operator")):
        return RouteDecision("human_handoff", "human", 0.9)
    if _contains(text, ("weather", "forecast")):
        return RouteDecision("general_web", "weather", 0.9)
    if _contains(text, ("euro", "exchange rate")):
        return RouteDecision("general_web", "fx", 0.9)
    account = _account(text)
    product = _product(text)
    if account is not None and product is not None:
        detail, confidence = account
        return RouteDecision(
            "account_support",
            detail,
            min(confidence, product),
            sequence=("account_support", "product_knowledge"),
        )
    if account is not None:
        detail, confidence = account
        return RouteDecision("account_support", detail, confidence)
    if product is not None:
        return RouteDecision("product_knowledge", "product", product)
    return RouteDecision("out_of_scope", "unsupported", 0.7)


def _account(text: str) -> tuple[str, float] | None:
    if _contains(text, ("decline", "declined")):
        return "decline", 0.88
    if _contains(text, ("connect", "internet", "wifi", "wi-fi")):
        return "connectivity", 0.88
    if _contains(text, ("deposited", "deposit", "yesterday")):
        return "receivables", 0.88
    if _contains(text, ("receiving setup", "my account", "machine model", "which machine")):
        return "profile", 0.84
    return None


def _product(text: str) -> float | None:
    if _contains(text, _PRODUCT_WORDS):
        return 0.86
    if "getnet" in text:
        return 0.55
    return None


def _continue(handoff: Handoff) -> RouteDecision | None:
    intent = str(handoff.payload.get("prior_intent") or "")
    detail = str(handoff.payload.get("prior_detail") or "")
    if intent not in _CONTINUABLE or not detail:
        return None
    return RouteDecision(intent, detail, 0.62, continued=True)


def _detail(message: str, intent: str) -> str:
    if intent != "general_web" and intent != "account_support" and intent != "product_knowledge":
        return intent
    table = _table(message)
    if table.intent == intent:
        return table.detail
    if intent == "general_web":
        return "weather" if "weather" in _fold(message) or "forecast" in _fold(message) else "fx"
    if intent == "account_support":
        return "receivables"
    return "product"


def _fold(message: str) -> str:
    normalized = unicodedata.normalize("NFKD", message)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _contains(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)
