"""Product answers from the corpus, and general lookup that cites no Getnet page."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.models import PublicSource
from app.llm.client import LLMClient
from app.orchestration.handoff import Handoff
from app.rag.retriever import MIN_SCORE, BM25Retriever, ChromaRetriever, Hit
from app.tools.web_search import WebSearch

PRODUCT_SYSTEM = """You answer questions about Getnet using only the passages in the user message.
If the passages do not state the fact, say that the public material does not support an answer.
Do not invent fees, deadlines, installment counts, or eligibility.
Do not use outside knowledge. Mention the passage titles you used.
"""


@dataclass
class KnowledgeResult:
    answer: str
    confidence: float
    sources: list[PublicSource] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    retrieval_scores: list[float] = field(default_factory=list)
    insufficient: bool = False


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
        if not strong:
            return KnowledgeResult(
                answer="",
                confidence=0.2,
                retrieval_scores=scores,
                insufficient=True,
            )
        generated = self._llm.answer(PRODUCT_SYSTEM, _prompt(message, strong))
        if generated:
            answer = generated
        else:
            blocks = "\n\n".join(hit.text.strip() for hit in strong)
            answer = f"Based on public Getnet material:\n\n{blocks}"
        return KnowledgeResult(
            answer=answer,
            confidence=min(0.95, strong[0].score),
            sources=[PublicSource(title=hit.title, url=hit.url) for hit in strong],
            retrieval_scores=scores,
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
