"""Single workflow owner. The router may run support and then knowledge on one turn."""

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
from app.domain.models import ClaimedStatement, PublicSource, Reply, ReviewRecord
from app.llm.client import LLMClient
from app.observability.hallucination_check import RetrievedPassage, StatedField, evaluate
from app.observability.metrics import MetricsStore
from app.observability.traces import TraceStore
from app.orchestration.handoff import Handoff as AgentHandoff
from app.orchestration.sessions import MemoryTurn, SessionStore
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
        sessions: SessionStore,
        metrics: MetricsStore,
    ) -> None:
        self.guardrail = guardrail
        self.router = router
        self.knowledge = knowledge
        self.support = support
        self.escalation = escalation
        self.traces = traces
        self.sessions = sessions
        self.metrics = metrics

    def handle(self, message: str, user_id: str, session_id: str | None = None) -> Reply:
        started = time.perf_counter()
        trace_id = str(uuid4())
        session_id = session_id or str(uuid4())
        route: list[str] = ["guardrail"]
        prior = self.sessions.latest(user_id, session_id)
        payload: dict[str, Any] = {"message": message, "user_id": user_id}
        if prior is not None:
            payload["prior_intent"] = prior.intent
            payload["prior_detail"] = prior.detail
            payload["prior_message"] = prior.topic
        incoming = AgentHandoff(
            trace_id=trace_id,
            intent="pending",
            confidence=1.0,
            payload=payload,
        )
        decision = self.guardrail.review(incoming)
        if not decision.allowed:
            return self._finish(
                trace_id=trace_id,
                user_id=user_id,
                session_id=session_id,
                route=route,
                intent="refused",
                outcome="refused",
                answer=_REFUSALS.get(decision.reason, _REFUSALS["injection"]),
                confidence=0.99,
                started=started,
                memory=MemoryTurn(message=message, intent="refused", detail=decision.reason, topic=message),
            )

        route.append("router")
        routed = self.router.route(incoming)
        query = message
        if routed.continued:
            prior_message = str(payload.get("prior_message") or "")
            if prior_message:
                query = prior_message
        current = AgentHandoff(
            trace_id=trace_id,
            intent=routed.intent,
            confidence=routed.confidence,
            payload={**payload, "message": query, "detail": routed.detail},
        )

        if routed.intent == "human_handoff" or routed.confidence < 0.45:
            reason = "human_requested" if routed.intent == "human_handoff" else "low_confidence"
            return self._escalate(
                trace_id,
                user_id,
                session_id,
                route,
                routed.intent,
                routed.detail,
                message,
                reason,
                started,
            )

        if routed.intent == "out_of_scope":
            return self._finish(
                trace_id=trace_id,
                user_id=user_id,
                session_id=session_id,
                route=route,
                intent="out_of_scope",
                outcome="refused",
                answer=(
                    "I can't help with that topic. I can answer questions about Getnet products, "
                    "your own sales and card machine, the weather, or an exchange rate."
                ),
                confidence=routed.confidence,
                started=started,
                memory=MemoryTurn(message=message, intent="out_of_scope", detail="unsupported", topic=message),
            )

        answers: list[str] = []
        tools: list[str] = []
        sources: list[PublicSource] = []
        claims: list[ClaimedStatement] = []
        stated: list[StatedField] = []
        payloads: dict[str, dict[str, Any]] = {}
        retrieved: list[RetrievedPassage] = []
        scores: list[float] = []
        confidences: list[float] = []
        retriever = "bm25"

        for step in routed.steps():
            if step == "general_web":
                route.append("knowledge")
                result = self.knowledge.answer_general(current)
                answers.append(result.answer)
                tools.extend(result.tools)
                confidences.append(result.confidence)
            elif step == "account_support":
                route.append("support")
                result = self.support.answer(current)
                answers.append(result.answer)
                tools.extend(result.tools)
                claims.extend(result.claims)
                stated.extend(result.stated)
                if result.tools:
                    payloads[result.tools[0]] = result.payload
                confidences.append(result.confidence)
            elif step == "product_knowledge":
                route.append("knowledge")
                result = self.knowledge.answer_product(current)
                scores.extend(result.retrieval_scores)
                retrieved.extend(result.retrieved)
                retriever = result.retriever_name
                if result.insufficient:
                    if answers:
                        answers.append(
                            "The public Getnet material does not support the rest of this question, "
                            "so I will not guess that part."
                        )
                    else:
                        return self._escalate(
                            trace_id,
                            user_id,
                            session_id,
                            route,
                            "product_knowledge",
                            "product",
                            message,
                            "insufficient_sources",
                            started,
                            retrieval_scores=scores,
                        )
                else:
                    answers.append(result.answer)
                    sources.extend(result.sources)
                    claims.extend(result.claims)
                    confidences.append(result.confidence)

        return self._finish(
            trace_id=trace_id,
            user_id=user_id,
            session_id=session_id,
            route=route,
            intent=routed.intent,
            outcome="answered",
            answer="\n\n".join(answers),
            confidence=min(confidences) if confidences else routed.confidence,
            tools=tools,
            sources=sources,
            retrieval_scores=scores,
            claims=claims,
            stated=stated,
            payloads=payloads,
            retrieved=retrieved,
            retriever=retriever,
            started=started,
            memory=MemoryTurn(
                message=message,
                intent=routed.intent,
                detail=routed.detail,
                topic=query if routed.continued else message,
            ),
        )

    def _escalate(
        self,
        trace_id: str,
        user_id: str,
        session_id: str,
        route: list[str],
        intent: str,
        detail: str,
        message: str,
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
            session_id=session_id,
            route=route,
            intent=intent,
            outcome="handoff",
            answer=answer,
            confidence=0.4,
            handoff=ticket,
            retrieval_scores=retrieval_scores or [],
            started=started,
            memory=MemoryTurn(message=message, intent=intent, detail=detail, topic=message),
        )

    def _finish(
        self,
        *,
        trace_id: str,
        user_id: str,
        session_id: str,
        route: list[str],
        intent: str,
        outcome: str,
        answer: str,
        confidence: float,
        started: float,
        memory: MemoryTurn,
        tools: list[str] | None = None,
        sources: list[PublicSource] | None = None,
        handoff: HandoffReceipt | None = None,
        retrieval_scores: list[float] | None = None,
        claims: list[ClaimedStatement] | None = None,
        stated: list[StatedField] | None = None,
        payloads: dict[str, dict[str, Any]] | None = None,
        retrieved: list[RetrievedPassage] | None = None,
        retriever: str = "bm25",
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
            session_id=session_id,
        )
        report = evaluate(
            intent=intent,
            outcome=outcome,
            claims=claims,
            stated=stated,
            payloads=payloads,
            sources=sources,
            retrieved=retrieved,
            retriever=retriever,
            tools=tools,
        )
        self.traces.put(
            ReviewRecord(
                trace_id=trace_id,
                user_id=user_id,
                session_id=session_id,
                route=route,  # type: ignore[arg-type]
                intent=intent,  # type: ignore[arg-type]
                tools=list(tools or []),
                sources=sources or [],
                retrieval_scores=list(retrieval_scores or []),
                outcome=outcome,  # type: ignore[arg-type]
                confidence=confidence,
                handoff=handoff,
                latency_ms=latency_ms,
                claimed_statements=report.claimed_statements,
                evidence=report.evidence,
                check_results=report.check_results,
                verdict=report.verdict,  # type: ignore[arg-type]
                verdict_confidence=report.verdict_confidence,
            )
        )
        self.sessions.remember(user_id, session_id, memory)
        self.metrics.record(outcome=outcome, verdict=report.verdict)
        return reply


def build_service(
    *,
    merchants: dict[str, Any],
    retriever: BM25Retriever | ChromaRetriever,
    llm: LLMClient,
    web: WebSearch,
    traces: TraceStore | None = None,
    sessions: SessionStore | None = None,
    metrics: MetricsStore | None = None,
) -> ChatService:
    return ChatService(
        guardrail=GuardrailAgent(),
        router=RouterAgent(llm),
        knowledge=KnowledgeAgent(retriever, web, llm),
        support=SupportAgent(merchants),
        escalation=EscalationAgent(),
        traces=traces or TraceStore(),
        sessions=sessions or SessionStore(),
        metrics=metrics or MetricsStore(),
    )
