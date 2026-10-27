"""HTTP surface: POST /v1/chat and GET /v1/traces/{trace_id}."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import Settings
from app.domain.models import ChatRequest, Reply, ReviewRecord
from app.llm.client import LLMClient, build_llm
from app.orchestration.service import build_service
from app.rag.corpus import load_corpus
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
    )
    app = FastAPI(title="Getnet Assist", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "Invalid request"})

    @app.post("/v1/chat", response_model=Reply)
    def create_chat(body: ChatRequest) -> Reply:
        return service.handle(body.message, body.user_id)

    @app.get("/v1/traces/{trace_id}", response_model=ReviewRecord)
    def read_trace(trace_id: str) -> ReviewRecord:
        try:
            UUID(trace_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Unknown trace") from exc
        record = service.traces.get(trace_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown trace")
        return record

    return app


app = create_app()
