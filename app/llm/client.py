"""LLM boundary. Tests pass a fake. The OpenAI client is used only with a key."""

from __future__ import annotations

import json
from typing import Protocol

ROUTER_SYSTEM = """You classify a Getnet merchant message.
Return JSON only, with one key "intent" whose value is exactly one of:
product_knowledge, account_support, general_web, human_handoff, out_of_scope.
product_knowledge: Getnet products or public policy (machines, Pix, antecipação, crediário, payment link).
account_support: this merchant's own deposit, receivables, or card-machine fault.
general_web: weather or foreign-exchange rate only.
human_handoff: the person asks for a human.
out_of_scope: anything else, including moving money or changing a contract.
Choose account_support when the merchant's own money or machine is the main need.
"""


class LLMClient(Protocol):
    def classify(self, message: str) -> str | None:
        """Return an intent name, or None when the model should not decide."""

    def answer(self, system: str, user: str) -> str | None:
        """Return grounded prose, or None to keep the extractive answer."""


class NullLLM:
    def classify(self, message: str) -> str | None:
        return None

    def answer(self, system: str, user: str) -> str | None:
        return None


class FakeLLM:
    """Scripted model for tests. A valid intent overrides the keyword table."""

    def __init__(self, intent: str | None = None, answer: str | None = None) -> None:
        self.intent = intent
        self._answer = answer

    def classify(self, message: str) -> str | None:
        return self.intent

    def answer(self, system: str, user: str) -> str | None:
        return self._answer


class OpenAICompatibleClient:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def classify(self, message: str) -> str | None:
        raw = self._complete(ROUTER_SYSTEM, message)
        if not raw:
            return None
        return _parse_intent(raw)

    def answer(self, system: str, user: str) -> str | None:
        return self._complete(system, user)

    def _complete(self, system: str, user: str) -> str | None:
        if not self.api_key:
            return None
        try:
            from openai import OpenAI
        except ImportError:
            return None
        kwargs: dict[str, str] = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        client = OpenAI(**kwargs)
        response = client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content
        return content.strip() if content else None


def build_llm(api_key: str, base_url: str, model: str) -> LLMClient:
    if not api_key:
        return NullLLM()
    return OpenAICompatibleClient(api_key, base_url, model)


def _parse_intent(raw: str) -> str | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    intent = payload.get("intent")
    return intent if isinstance(intent, str) else None
