"""HTTP surface: chat, the review record, the check read, and the metrics snapshot."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import Settings
from app.domain.models import ChatRequest, CheckResponse, MetricsSnapshot, Reply, ReviewRecord
from app.llm.client import LLMClient, build_llm
from app.observability.metrics import MetricsStore, corpus_age_days
from app.orchestration.service import build_service
from app.rag.corpus import load_corpus
from app.rag.ingest import ingest_specified_urls
from app.rag.retriever import build_retriever
from app.tools.store import load_merchants
from app.tools.web_search import HttpWebSearch, WebSearch

logging.basicConfig(level=logging.INFO)


def create_app(
    *,
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    web_search: WebSearch | None = None,
) -> FastAPI:
    resolved = settings or Settings.from_env()
    if resolved.ingest_on_start:
        try:
            ingest_specified_urls(resolved.corpus_dir)
        except Exception:
            logging.getLogger(__name__).warning(
                "Could not download the Getnet pages; using the corpus already on disk",
                exc_info=True,
            )
    documents = load_corpus(resolved.corpus_dir)
    retriever = build_retriever(documents, resolved)
    model = llm if llm is not None else build_llm(
        resolved.openai_api_key,
        resolved.openai_base_url,
        resolved.openai_model,
    )
    lookup = web_search if web_search is not None else HttpWebSearch()
    service = build_service(
        merchants=load_merchants(resolved.merchants_path),
        retriever=retriever,
        llm=model,
        web=lookup,
        metrics=MetricsStore(corpus_age_days=corpus_age_days(resolved.corpus_dir)),
    )
    app = FastAPI(title="Getnet Assist", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "Invalid request"})

    def load_trace(trace_id: str) -> ReviewRecord:
        try:
            UUID(trace_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Unknown trace") from exc
        record = service.traces.get(trace_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown trace")
        return record

    @app.post("/v1/chat", response_model=Reply)
    def create_chat(body: ChatRequest) -> Reply:
        return service.handle(body.message, body.user_id, body.session_id)

    @app.get("/v1/metrics", response_model=MetricsSnapshot)
    def read_metrics() -> MetricsSnapshot:
        return service.metrics.snapshot()

    @app.get("/v1/traces/{trace_id}/check", response_model=CheckResponse)
    def read_check(trace_id: str) -> CheckResponse:
        record = load_trace(trace_id)
        return CheckResponse(
            trace_id=record.trace_id,
            verdict=record.verdict,
            verdict_confidence=record.verdict_confidence,
            check_results=record.check_results,
        )

    @app.get("/v1/traces/{trace_id}", response_model=ReviewRecord)
    def read_trace(trace_id: str) -> ReviewRecord:
        return load_trace(trace_id)

    return app


app = create_app()
