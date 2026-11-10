"""Request and response models for chat, the review record, and the check read."""

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
ClaimKind = Literal["product", "support"]
CheckName = Literal["anchor", "tool_payload", "structured_output"]
CheckStatus = Literal["pass", "fail", "not_applicable"]
VerdictName = Literal["hallucinated", "verified", "unverified"]
RetrieverName = Literal["bm25", "chroma"]


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
    session_id: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    answer: str = Field(min_length=1)
    route: list[RouteName] = Field(min_length=1)
    sources: list[PublicSource]
    confidence: float = Field(ge=0, le=1)
    handoff: Handoff | None
    tools_used: list[ToolName]
    session_id: str = Field(min_length=1, max_length=64)


class ClaimedStatement(BaseModel):
    """One assertion. Support statements store field names, never field values."""

    model_config = ConfigDict(extra="forbid")

    kind: ClaimKind
    text: str = ""
    citations: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)


class SourceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["retrieved_source"] = "retrieved_source"
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    retriever: RetrieverName
    score: float


class ToolEvidence(BaseModel):
    """Field names and whether they matched. Values are not stored."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["tool_comparison"] = "tool_comparison"
    tool: str = Field(min_length=1)
    fields: list[str]
    matched: bool


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CheckName
    status: CheckStatus


class ReviewRecord(BaseModel):
    """Operator view. Raw customer payloads are not fields on this model."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    user_id: str
    session_id: str = Field(min_length=1, max_length=64)
    route: list[RouteName]
    intent: IntentName
    tools: list[str]
    sources: list[PublicSource]
    retrieval_scores: list[float]
    outcome: OutcomeName
    confidence: float = Field(ge=0, le=1)
    handoff: Handoff | None
    latency_ms: int = Field(ge=0)
    claimed_statements: list[ClaimedStatement]
    evidence: list[SourceEvidence | ToolEvidence]
    check_results: list[CheckResult]
    verdict: VerdictName
    verdict_confidence: float = Field(ge=0, le=1)


class CheckResponse(BaseModel):
    """Slim hallucination read. No answer, sources, claims, or tool values."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    verdict: VerdictName
    verdict_confidence: float = Field(ge=0, le=1)
    check_results: list[CheckResult]


class MetricsSnapshot(BaseModel):
    """Aggregate counters only. No user id, answer, or tool value."""

    model_config = ConfigDict(extra="forbid")

    requests: int = Field(ge=0)
    answered: int = Field(ge=0)
    refused: int = Field(ge=0)
    handoffs: int = Field(ge=0)
    verified: int = Field(ge=0)
    hallucinated: int = Field(ge=0)
    unverified: int = Field(ge=0)
    corpus_age_days: int = Field(ge=0)
    corpus_stale: bool
    alerts: list[str]
