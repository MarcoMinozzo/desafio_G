"""Single workflow owner. One specialist runs after the guardrail and the router."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from app.agents.escalation import EscalationAgent
from app.agents.guardrail import GuardrailAgent
from app.agents.knowledge import KnowledgeAgent
from app.agents.router import RouterAgent
from app.agents.support import SupportAgent
from app.domain.models import Handoff as HandoffReceipt
from app.domain.models import PublicSource, Reply, ReviewRecord
from app.llm.client import LLMClient
from app.observability.traces import TraceStore
from app.orchestration.handoff import Handoff as AgentHandoff
from app.rag.retriever import BM25Retriever, ChromaRetriever
from app.tools.web_search import WebSearch

_REFUSALS = {
    "empty": "Send a question so I can help.",
    "injection": "I can't follow instructions that try to override the rules or reveal hidden prompts.",
    "cross_customer": (
        "I can only look at the account for the user on this request. "
        "I will not return another customer's data."
    ),
}


class ChatService:
    def __init__(
        self,
        *,
        guardrail: GuardrailAgent,
        router: RouterAgent,
        knowledge: KnowledgeAgent,
        support: SupportAgent,
        escalation: EscalationAgent,
        traces: TraceStore,
    ) -> None:
        self.guardrail = guardrail
        self.router = router
        self.knowledge = knowledge
        self.support = support
        self.escalation = escalation
        self.traces = traces

    def handle(self, message: str, user_id: str) -> Reply:
        started = time.perf_counter()
        trace_id = str(uuid4())
        route: list[str] = ["guardrail"]
        incoming = AgentHandoff(
            trace_id=trace_id,
            intent="pending",
            confidence=1.0,
            payload={"message": message, "user_id": user_id},
        )
        decision = self.guardrail.review(incoming)
        if not decision.allowed:
            return self._finish(
                trace_id=trace_id,
                user_id=user_id,
                route=route,
                intent="refused",
                outcome="refused",
                answer=_REFUSALS.get(decision.reason, _REFUSALS["injection"]),
                confidence=0.99,
                started=started,
            )

        route.append("router")
        routed = self.router.route(incoming)
        current = AgentHandoff(
            trace_id=trace_id,
            intent=routed.intent,
            confidence=routed.confidence,
            payload={**incoming.payload, "detail": routed.detail},
        )

        if routed.intent == "human_handoff" or routed.confidence < 0.45:
            reason = "human_requested" if routed.intent == "human_handoff" else "low_confidence"
            return self._escalate(trace_id, user_id, route, routed.intent, reason, started)

        if routed.intent == "out_of_scope":
            return self._finish(
                trace_id=trace_id,
                user_id=user_id,
                route=route,
                intent="out_of_scope",
                outcome="refused",
                answer=(
                    "I can't help with that topic. I can answer questions about Getnet products, "
                    "your own sales and card machine, the weather, or an exchange rate."
                ),
                confidence=routed.confidence,
                started=started,
            )

        if routed.intent == "general_web":
            route.append("knowledge")
            result = self.knowledge.answer_general(current)
            return self._finish(
                trace_id=trace_id,
                user_id=user_id,
                route=route,
                intent="general_web",
                outcome="answered",
                answer=result.answer,
                confidence=result.confidence,
                tools=result.tools,
                started=started,
            )

        if routed.intent == "account_support":
            route.append("support")
            result = self.support.answer(current)
            return self._finish(
                trace_id=trace_id,
                user_id=user_id,
                route=route,
                intent="account_support",
                outcome="answered",
                answer=result.answer,
                confidence=result.confidence,
                tools=result.tools,
                started=started,
            )

        route.append("knowledge")
        result = self.knowledge.answer_product(current)
        if result.insufficient:
            return self._escalate(
                trace_id,
                user_id,
                route,
                "product_knowledge",
                "insufficient_sources",
                started,
                retrieval_scores=result.retrieval_scores,
            )
        return self._finish(
            trace_id=trace_id,
            user_id=user_id,
            route=route,
            intent="product_knowledge",
            outcome="answered",
            answer=result.answer,
            confidence=result.confidence,
            sources=result.sources,
            retrieval_scores=result.retrieval_scores,
            started=started,
        )

    def _escalate(
        self,
        trace_id: str,
        user_id: str,
        route: list[str],
        intent: str,
        reason: str,
        started: float,
        retrieval_scores: list[float] | None = None,
    ) -> Reply:
        route.append("escalation")
        ticket = self.escalation.open(reason)  # type: ignore[arg-type]
        if reason == "human_requested":
            answer = f"I'll hand this to a person. Reference {ticket.reference}."
        elif reason == "low_confidence":
            answer = (
                f"I am not confident enough to answer, so a person will take it. "
                f"Reference {ticket.reference}."
            )
        else:
            answer = (
                "The public Getnet material does not support an answer, so I will not guess. "
                f"A person can take it from here. Reference {ticket.reference}."
            )
        return self._finish(
            trace_id=trace_id,
            user_id=user_id,
            route=route,
            intent=intent,
            outcome="handoff",
            answer=answer,
            confidence=0.4,
            handoff=ticket,
            retrieval_scores=retrieval_scores or [],
            started=started,
        )

    def _finish(
        self,
        *,
        trace_id: str,
        user_id: str,
        route: list[str],
        intent: str,
        outcome: str,
        answer: str,
        confidence: float,
        started: float,
        tools: list[str] | None = None,
        sources: list[PublicSource] | None = None,
        handoff: HandoffReceipt | None = None,
        retrieval_scores: list[float] | None = None,
    ) -> Reply:
        latency_ms = int((time.perf_counter() - started) * 1000)
        reply = Reply(
            trace_id=trace_id,
            answer=answer,
            route=route,  # type: ignore[arg-type]
            sources=sources or [],
            confidence=confidence,
            handoff=handoff,
            tools_used=tools or [],  # type: ignore[arg-type]
        )
        self.traces.put(
            ReviewRecord(
                trace_id=trace_id,
                user_id=user_id,
                route=route,  # type: ignore[arg-type]
                intent=intent,  # type: ignore[arg-type]
                tools=list(tools or []),
                sources=sources or [],
                retrieval_scores=list(retrieval_scores or []),
                outcome=outcome,  # type: ignore[arg-type]
                confidence=confidence,
                handoff=handoff,
                latency_ms=latency_ms,
            )
        )
        return reply


def build_service(
    *,
    merchants: dict[str, Any],
    retriever: BM25Retriever | ChromaRetriever,
    llm: LLMClient,
    web: WebSearch,
    traces: TraceStore | None = None,
) -> ChatService:
    store = traces or TraceStore()
    return ChatService(
        guardrail=GuardrailAgent(),
        router=RouterAgent(llm),
        knowledge=KnowledgeAgent(retriever, web, llm),
        support=SupportAgent(merchants),
        escalation=EscalationAgent(),
        traces=store,
    )
