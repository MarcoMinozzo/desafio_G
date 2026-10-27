# Implementation Plan: Getnet Assist Orchestration

**Branch**: `001-agent-orchestration` | **Date**: 2026-10-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-agent-orchestration/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Getnet Assist answers one merchant message through an in-process handoff of
five roles: guardrail, router, knowledge, account support, and escalation.
Product answers are grounded in a curated public corpus (BM25 by default,
Chroma embeddings only when `OPENAI_API_KEY` is set). Account answers use a
fixture store scoped to `user_id`. Weather and exchange rates use a web
lookup that is never evidence for Getnet policy. Without a model key, the
router uses a deterministic intent table and the knowledge role returns an
extractive answer with citations, so Docker and the evaluation set run
offline.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: FastAPI, Pydantic v2, Uvicorn, rank-bm25, httpx, pytest. Optional extras: openai, chromadb.

**Storage**: Curated Markdown corpus in `data/corpus/`; merchant fixture JSON in `data/merchants.json`; evaluation YAML in `data/evaluation.yaml`; in-memory trace store. Chroma persistent directory only when embeddings are enabled.

**Testing**: pytest with FastAPI TestClient, a fake LLM, and a fake web lookup. No network in the default suite.

**Target Platform**: Linux container (single service) and local CPython 3.12.

**Project Type**: web-service

**Performance Goals**: The ten briefing messages complete in under 5 seconds total on the lexical path, with no live model.

**Constraints**: One container. Endpoints limited to `POST /v1/chat` and `GET /v1/traces/{trace_id}`. Product answers cite a source or admit uncertainty. Tools accept only the request `user_id`. Tests assert route and tool, not prose. Offline lexical answers work with no API key.

**Scale/Scope**: One demonstration merchant (`cliente1988`), a small public corpus (machines, Pix, antecipação, payment link, crediário, terminal help), and the ten briefing scenarios.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Grounded Answers**: Knowledge generation is extractive or prompted only
  with retrieved passages. Low retrieval score becomes uncertainty or
  handoff. PASS.
- **II. Customer Data Isolation**: Support tools take `user_id` from the
  request, never from the message. Traces store `user_id` and tool names, not
  raw records. PASS.
- **III. Orchestration Testable Without a Live Model**: `LLMClient` is an
  interface. Tests inject a fake. The intent table covers the evaluation set
  when no key is set. PASS.
- **IV. One Container**: `docker-compose.yml` runs one app service. Handoff is
  in-process. BM25 is built from files shipped in the image. PASS.
- **V. No Extra Surface**: No health, login, crawl, or dashboard routes.
  PASS.

Post-design re-check: contracts, data model, and quickstart introduce no
additional endpoints or live CRM. PASS.

## Project Structure

### Documentation (this feature)

```text
specs/001-agent-orchestration/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── chat.openapi.yaml
└── tasks.md
```

### Source Code (repository root)

```text
app/
├── main.py
├── config.py
├── domain/models.py
├── llm/client.py
├── orchestration/handoff.py
├── orchestration/service.py
├── agents/guardrail.py
├── agents/router.py
├── agents/knowledge.py
├── agents/support.py
├── agents/escalation.py
├── tools/merchant.py
├── tools/receivables.py
├── tools/terminal.py
├── tools/web_search.py
├── rag/corpus.py
├── rag/retriever.py
└── observability/traces.py
data/
├── corpus/
├── merchants.json
└── evaluation.yaml
tests/
├── conftest.py
├── test_contract.py
├── test_orchestration.py
├── test_retrieval.py
├── test_guardrail.py
└── test_evaluation.py
Dockerfile
docker-compose.yml
pyproject.toml
README.md
```

**Structure Decision**: Single Python service under `app/`. Agents call tools
and the retriever through plain functions. `ChatService` in
`app/orchestration/service.py` is the only workflow owner.

## Complexity Tracking

No constitution violations.
