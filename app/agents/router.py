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


@dataclass(frozen=True)
class RouteDecision:
    intent: str
    detail: str
    confidence: float


class RouterAgent:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def route(self, handoff: Handoff) -> RouteDecision:
        message = str(handoff.payload.get("message", ""))
        model_intent = self._llm.classify(message)
        if model_intent in ALLOWED:
            return RouteDecision(model_intent, _detail(message, model_intent), 0.8)
        return _table(message)


def _table(message: str) -> RouteDecision:
    text = _fold(message)
    if _contains(text, ("talk to a human", "talk to a person", "speak to a person", "human operator")):
        return RouteDecision("human_handoff", "human", 0.9)
    if _contains(text, ("weather", "forecast")):
        return RouteDecision("general_web", "weather", 0.9)
    if _contains(text, ("euro", "exchange rate")):
        return RouteDecision("general_web", "fx", 0.9)
    if _contains(text, ("decline", "declined")):
        return RouteDecision("account_support", "decline", 0.88)
    if _contains(text, ("connect", "internet", "wifi", "wi-fi")):
        return RouteDecision("account_support", "connectivity", 0.88)
    if _contains(text, ("deposited", "deposit", "yesterday")):
        return RouteDecision("account_support", "receivables", 0.88)
    if _contains(text, ("receiving setup", "my account", "machine model", "which machine")):
        return RouteDecision("account_support", "profile", 0.84)
    if _contains(
        text,
        (
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
        ),
    ):
        return RouteDecision("product_knowledge", "product", 0.86)
    if "getnet" in text:
        return RouteDecision("product_knowledge", "product", 0.55)
    return RouteDecision("out_of_scope", "unsupported", 0.7)


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
