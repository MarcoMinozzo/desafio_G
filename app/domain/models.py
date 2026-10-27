"""Request and response models for the two public routes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RouteName = Literal["guardrail", "router", "knowledge", "support", "escalation"]
ToolName = Literal["get_merchant_account", "get_receivables", "diagnose_terminal", "web_search"]
IntentName = Literal[
    "product_knowledge",
    "account_support",
    "general_web",
    "human_handoff",
    "out_of_scope",
    "refused",
]
OutcomeName = Literal["answered", "refused", "handoff"]
HandoffReason = Literal["human_requested", "low_confidence", "insufficient_sources"]


class PublicSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    url: str = Field(min_length=1)


class Handoff(BaseModel):
    """Customer-facing handoff receipt. Reference matches ESC-[A-Z0-9]{8}."""

    model_config = ConfigDict(extra="forbid")

    reference: str = Field(pattern=r"^ESC-[A-Z0-9]{8}$")
    reason: HandoffReason


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    answer: str = Field(min_length=1)
    route: list[RouteName] = Field(min_length=1)
    sources: list[PublicSource]
    confidence: float = Field(ge=0, le=1)
    handoff: Handoff | None
    tools_used: list[ToolName]


class ReviewRecord(BaseModel):
    """Operator view. Raw customer payloads are not fields on this model."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    user_id: str
    route: list[RouteName]
    intent: IntentName
    tools: list[str]
    sources: list[PublicSource]
    retrieval_scores: list[float]
    outcome: OutcomeName
    confidence: float = Field(ge=0, le=1)
    handoff: Handoff | None
    latency_ms: int = Field(ge=0)
