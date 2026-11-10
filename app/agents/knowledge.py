"""Product answers from the corpus, and general lookup that cites no Getnet page."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.domain.models import ClaimedStatement, PublicSource
from app.llm.client import LLMClient
from app.observability.hallucination_check import RetrievedPassage
from app.orchestration.handoff import Handoff
from app.rag.retriever import MIN_SCORE, BM25Retriever, ChromaRetriever, Hit
from app.tools.web_search import WebSearch

PRODUCT_SYSTEM = """You answer questions about Getnet using only the passages in the user message.
If the passages do not state the fact, say that the public material does not support an answer.
Do not invent fees, deadlines, installment counts, or eligibility.
Do not use outside knowledge.
Return JSON only, with keys "answer" and "claims".
"answer" is the prose reply. "claims" is a list of objects with "text" and "citations".
Each citation is a passage URL copied from the user message. Do not cite any other URL.
"""


@dataclass
class KnowledgeResult:
    answer: str
    confidence: float
    sources: list[PublicSource] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    retrieval_scores: list[float] = field(default_factory=list)
    insufficient: bool = False
    claims: list[ClaimedStatement] = field(default_factory=list)
    retrieved: list[RetrievedPassage] = field(default_factory=list)
    retriever_name: str = "bm25"


class KnowledgeAgent:
    def __init__(self, retriever: BM25Retriever | ChromaRetriever, web: WebSearch, llm: LLMClient) -> None:
        self._retriever = retriever
        self._web = web
        self._llm = llm

    def answer_product(self, handoff: Handoff) -> KnowledgeResult:
        message = str(handoff.payload.get("message", ""))
        hits = self._retriever.search(message, k=3)
        qualified = [hit for hit in hits if hit.score >= MIN_SCORE]
        if qualified:
            cutoff = qualified[0].score * 0.94
            strong = [hit for hit in qualified if hit.score >= cutoff]
        else:
            strong = []
        scores = [hit.score for hit in hits]
        retrieved = [RetrievedPassage(title=hit.title, url=hit.url, score=hit.score) for hit in hits]
        retriever_name = getattr(self._retriever, "name", "bm25")
        if not strong:
            return KnowledgeResult(
                answer="",
                confidence=0.2,
                retrieval_scores=scores,
                insufficient=True,
                retrieved=retrieved,
                retriever_name=retriever_name,
            )
        generated = self._llm.answer(PRODUCT_SYSTEM, _prompt(message, strong))
        parsed = _claims_from_model(generated) if generated else None
        if generated is None:
            answer = "Based on public Getnet material:\n\n" + "\n\n".join(hit.text.strip() for hit in strong)
            claims = [
                ClaimedStatement(kind="product", text=hit.text.strip() or hit.title, citations=[hit.url])
                for hit in strong
            ]
        elif parsed is None:
            answer = generated
            claims = []
        else:
            answer, claims = parsed
            if not answer:
                answer = "Based on public Getnet material:\n\n" + "\n\n".join(hit.text.strip() for hit in strong)
        return KnowledgeResult(
            answer=answer,
            confidence=min(0.95, strong[0].score),
            sources=[PublicSource(title=hit.title, url=hit.url) for hit in strong],
            retrieval_scores=scores,
            claims=claims,
            retrieved=retrieved,
            retriever_name=retriever_name,
        )

    def answer_general(self, handoff: Handoff) -> KnowledgeResult:
        message = str(handoff.payload.get("message", ""))
        kind = str(handoff.payload.get("detail", "fx"))
        text = self._web.lookup(kind, message)
        if not text:
            answer = (
                "The general public lookup is unavailable right now. "
                "This is not a Getnet product answer."
            )
            confidence = 0.35
        else:
            answer = text
            confidence = 0.8
        return KnowledgeResult(answer=answer, confidence=confidence, tools=["web_search"])


def _prompt(message: str, hits: list[Hit]) -> str:
    passages = "\n\n".join(f"Title: {hit.title}\nURL: {hit.url}\n{hit.text}" for hit in hits)
    return f"Question: {message}\n\nPassages:\n{passages}"


def _claims_from_model(raw: str) -> tuple[str, list[ClaimedStatement]] | None:
    """Read a claim list the model emitted. Prose is not scanned for citations."""

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
    if not isinstance(payload, dict) or not isinstance(payload.get("claims"), list):
        return None
    claims: list[ClaimedStatement] = []
    for item in payload["claims"]:
        if not isinstance(item, dict):
            return None
        text = item.get("text", "")
        citations = item.get("citations", [])
        if not isinstance(text, str) or not isinstance(citations, list):
            return None
        if not all(isinstance(url, str) and url for url in citations):
            return None
        claims.append(ClaimedStatement(kind="product", text=text, citations=list(citations)))
    answer = payload.get("answer", "")
    return (answer if isinstance(answer, str) else "", claims)
