# Research: Getnet Assist Orchestration

## Decision: Python 3.12 and FastAPI

- **Decision**: Implement the service in Python 3.12 with FastAPI and Pydantic v2.
- **Rationale**: The brief points at an HTTP JSON endpoint and a RAG pipeline. FastAPI gives a small typed surface that matches the two allowed routes. Pydantic v2 enforces the request limits in one place.
- **Alternatives considered**: Node.js with a custom server adds a second ecosystem for the same two routes. A CLI-only demo would miss the required POST contract.

## Decision: In-process typed handoff

- **Decision**: Agents exchange a `Handoff` dataclass (`trace_id`, intent, confidence, payload) inside one process.
- **Rationale**: The constitution requires one container and tests without a broker. A queue would add a service the evaluation never calls.
- **Alternatives considered**: Redis or an internal asyncio queue. Rejected because they hide the workflow and break the offline test path.

## Decision: BM25 by default, Chroma only with a key

- **Decision**: `rank-bm25` over the curated corpus is the default retriever. When `OPENAI_API_KEY` is set and `chromadb` imports, the service also builds a Chroma collection with `text-embedding-3-small` and prefers it. If either is missing, retrieval stays on BM25.
- **Rationale**: SC-008 requires a grounded product answer with no paid language service. Embeddings cannot be the only path. Chroma still satisfies the approved design when a key exists.
- **Alternatives considered**: FAISS, a hand-rolled cosine store, or embeddings always. FAISS and a custom store duplicate Chroma. Embeddings-only fails the offline gate.

## Decision: Extractive answers without a model, prompted answers with one

- **Decision**: With no key, the knowledge role returns the top passages plus their titles and URLs, and says when the score is below `0.15` normalized BM25. With a key, the same passages are the only context in the prompt. The prompt forbids fees, deadlines, and limits that are not in the passages.
- **Rationale**: Grounding is a constitution rule. Extractive output cannot invent a number that is not in the corpus.
- **Alternatives considered**: Always calling a model. Rejected because Docker and pytest must pass with no key.

## Decision: Deterministic router plus optional structured model

- **Decision**: `IntentTable` classifies the ten briefing messages and the handoff, injection-adjacent, and out-of-scope phrases. If a model key exists, the router asks for a JSON intent and uses it only when it is one of `product_knowledge`, `account_support`, `general_web`, `human_handoff`, `out_of_scope`. Otherwise the table wins.
- **Rationale**: Tests and the evaluation set must not depend on model wording. The table is the reliability floor. The model remains available for unseen phrasing.
- **Alternatives considered**: Model-only routing. Rejected because a single paraphrase change would fail the suite.

## Decision: Web lookup is Open-Meteo and Frankfurter

- **Decision**: Weather uses Open-Meteo (Porto Alegre coordinates -30.0346, -51.2177). Euro rate uses Frankfurter (`EUR` base against `BRL`). Tests replace this with a fake. Failure returns an unavailable general answer, never a Getnet passage.
- **Rationale**: Both APIs are keyless and match the two general scenarios. They are not Getnet sources.
- **Alternatives considered**: A search-engine HTML scrape. Rejected because it is brittle and mixes product pages into general questions.

## Decision: Fixture merchant store

- **Decision**: `data/merchants.json` holds `cliente1988` only. Tools look up the request `user_id` and return a not-found result for anyone else. They do not parse a second identifier out of the message.
- **Rationale**: Isolation is stronger when the tool cannot see other keys as a query parameter from the user text.
- **Alternatives considered**: A SQLite CRM. Rejected as extra surface for one demonstration merchant.

## Decision: Traces in memory and JSON logs

- **Decision**: Each chat writes one trace (route, intent, tools, retrieval scores, latency, outcome, sources, handoff) to an in-memory map and a single JSON log line on stdout. `GET /v1/traces/{trace_id}` returns that record. Raw tool payloads are not stored.
- **Rationale**: Meets the operator story and the constitution log rule without a dashboard.
- **Alternatives considered**: OpenTelemetry in the core image. Described in the README as the production step, not built, per the approved scope.

## Decision: Corpus is an original summary, not a page dump

- **Decision**: `data/corpus/*.md` files are short original summaries of public Getnet topics, each with `title` and `url` front matter pointing at https://www.getnet.net/ or https://www.getnet.net/en. They do not copy site pages verbatim and they do not state fees or installment counts the public pages do not state.
- **Rationale**: Grounding needs real topics. Copyright and the "do not invent" rule both forbid pasted pages and made-up numbers.
- **Alternatives considered**: Live crawl on startup. Rejected by constitution principle V and by offline startup.
