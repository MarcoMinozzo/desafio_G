# Tasks: Getnet Assist Orchestration

**Input**: Design documents from `/specs/001-agent-orchestration/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Included. The spec requires a repeatable evaluation set, and the constitution requires route, tool, and `user_id` assertions without a live model.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Single Python service: `app/`, `tests/`, `data/` at repository root

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create the `app` package layout from `specs/001-agent-orchestration/plan.md` and declare FastAPI, Pydantic v2, Uvicorn, rank-bm25, httpx, and pytest in `pyproject.toml`
- [X] T002 [P] Add Python ignore patterns (`__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `dist/`, `*.egg-info/`, `.env`) to `.gitignore`
- [X] T003 [P] Add Docker ignore patterns (`.venv/`, `__pycache__/`, `.git/`, `.env`) to `.dockerignore`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Create `ChatRequest`, `Reply`, `PublicSource`, `Handoff`, and `ReviewRecord` in `app/domain/models.py`. Enforce `message` trimmed length 1–4000, `user_id` length 1–64 and pattern `^[A-Za-z0-9_-]+$`, `confidence` from 0 to 1, route names `guardrail|router|knowledge|support|escalation`, tool names `get_merchant_account|get_receivables|diagnose_terminal|web_search`, handoff reference `ESC-[A-Z0-9]{8}`, handoff reason `human_requested|low_confidence|insufficient_sources`, intent `product_knowledge|account_support|general_web|human_handoff|out_of_scope|refused`, outcome `answered|refused|handoff`
- [X] T005 [P] Load `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL` in `app/config.py` with empty key as the offline default
- [X] T006 [P] Implement an in-memory review store that omits raw customer payloads in `app/observability/traces.py`
- [X] T007 Implement `LLMClient` plus `FakeLLM` and an OpenAI-compatible client in `app/llm/client.py`
- [X] T008 Define the in-process `Handoff` (`trace_id`, intent, confidence, payload) in `app/orchestration/handoff.py`
- [X] T009 Expose only `POST /v1/chat` and `GET /v1/traces/{trace_id}` in `app/main.py`, returning 422 for a `user_id` outside `^[A-Za-z0-9_-]+$` and 404 for an unknown trace

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Ask about Getnet products (Priority: P1) 🎯 MVP

**Goal**: A product question returns a cited public Getnet answer or an explicit uncertainty

**Independent Test**: Retrieval for antecipação and Payment Link returns those documents offline, and a product chat cites a source

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T010 [P] [US1] Write retrieval tests for antecipação and Payment Link in `tests/test_retrieval.py`

### Implementation for User Story 1

- [X] T011 [P] [US1] Write original corpus summaries with `title` and `url` front matter for machines, Pix, antecipação, payment link, crediário, and terminal help in `data/corpus/`
- [X] T012 [US1] Load corpus documents in `app/rag/corpus.py`
- [X] T013 [US1] Implement BM25 retrieval and the optional Chroma path (only when `OPENAI_API_KEY` is set and chromadb imports) in `app/rag/retriever.py`, treating normalized BM25 below `0.15` as insufficient
- [X] T014 [US1] Implement the knowledge agent in `app/agents/knowledge.py` so a product answer cites `PublicSource` items or sets handoff reason `insufficient_sources`

**Checkpoint**: User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Resolve the merchant's own account (Priority: P1)

**Goal**: Deposit, connectivity, and decline questions use only the caller's fixture record

**Independent Test**: `cliente1988` receivables and terminal diagnosis succeed; any other `user_id` is not-found and does not return the fixture amounts

### Tests for User Story 2 ⚠️

- [X] T015 [P] [US2] Write account-scope tests in `tests/test_orchestration.py` for deposit, connectivity, decline, and an unknown user

### Implementation for User Story 2

- [X] T016 [P] [US2] Create the `cliente1988` fixture in `data/merchants.json` with `pix_enabled`, `receiving_setup`, `machine_model`, yesterday's receivable (`sales_label` `yesterday`, `amount_brl` >= 0, `expected_deposit`, `status` `scheduled`), and terminal symptoms `connectivity` and `decline`
- [X] T017 [P] [US2] Implement `get_merchant_account` scoped to the request `user_id` in `app/tools/merchant.py`
- [X] T018 [P] [US2] Implement `get_receivables` scoped to the request `user_id` in `app/tools/receivables.py`
- [X] T019 [P] [US2] Implement `diagnose_terminal` for symptoms `connectivity` and `decline` in `app/tools/terminal.py`
- [X] T020 [US2] Implement the support agent in `app/agents/support.py` so it calls those tools and never accepts a user id from the message text

**Checkpoint**: User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Direct each message to the right specialist (Priority: P1)

**Goal**: Each briefing message reaches the specialist and fact in the evaluation set

**Independent Test**: All 10 rows in `data/evaluation.yaml` match intent, `route_contains`, and `tools_contain`

### Tests for User Story 3 ⚠️

- [X] T021 [P] [US3] Add the ten briefing rows to `data/evaluation.yaml` and assert them in `tests/test_evaluation.py`

### Implementation for User Story 3

- [X] T022 [US3] Implement the intent table and optional structured model override in `app/agents/router.py` for intents `product_knowledge`, `account_support`, `general_web`, `human_handoff`, and `out_of_scope`
- [X] T023 [US3] Own the workflow in `app/orchestration/service.py` so one primary specialist runs and account need outranks a general product explanation

**Checkpoint**: The evaluation set passes on the offline path

---

## Phase 6: User Story 4 - Answer general questions without pretending they are Getnet (Priority: P2)

**Goal**: Weather and euro questions use a general lookup and cite no Getnet source

**Independent Test**: Porto Alegre weather and the euro rate return `web_search` with an empty `sources` list

### Tests for User Story 4 ⚠️

- [X] T024 [P] [US4] Assert both general scenarios keep Getnet `sources` empty in `tests/test_evaluation.py`

### Implementation for User Story 4

- [X] T025 [US4] Implement `web_search` with Open-Meteo for Porto Alegre (`-30.0346`, `-51.2177`) and Frankfurter for EUR/BRL, plus a fake for tests, in `app/tools/web_search.py`
- [X] T026 [US4] Use `web_search` from the knowledge path only for `general_web` inside `app/agents/knowledge.py`, and on lookup failure say the general fact is unavailable

**Checkpoint**: General answers stay separate from the Getnet corpus

---

## Phase 7: User Story 5 - Refuse unsafe or unsupported requests (Priority: P2)

**Goal**: Injection, cross-customer access, and unsupported topics stop before account facts

**Independent Test**: Three refusal checks return `outcome=refused` and no receivable amount

### Tests for User Story 5 ⚠️

- [X] T027 [P] [US5] Write injection, cross-customer, and unsupported-topic tests in `tests/test_guardrail.py`

### Implementation for User Story 5

- [X] T028 [US5] Implement `GuardrailAgent` in `app/agents/guardrail.py` for empty messages, instruction override, and a second customer identifier
- [X] T029 [US5] Map `out_of_scope` to `outcome=refused` in `app/orchestration/service.py` with route starting at `guardrail` and no support tool call

**Checkpoint**: Refusals leak zero account facts

---

## Phase 8: User Story 6 - Hand off when the assistant should not guess (Priority: P2)

**Goal**: A human request or an unsupported Getnet fact returns `ESC-[A-Z0-9]{8}` and a reason

**Independent Test**: "I want to talk to a human" yields `outcome=handoff` and reason `human_requested`

### Tests for User Story 6 ⚠️

- [X] T030 [P] [US6] Write the human-handoff test in `tests/test_orchestration.py`

### Implementation for User Story 6

- [X] T031 [US6] Implement `EscalationAgent` in `app/agents/escalation.py` with reasons `human_requested`, `low_confidence`, and `insufficient_sources`
- [X] T032 [US6] Route human requests and insufficient product sources to escalation in `app/orchestration/service.py`

**Checkpoint**: Handoff replies include a reference and do not invent policy

---

## Phase 9: User Story 7 - Review how a reply was produced (Priority: P3)

**Goal**: An operator can read specialist, outcome, sources, and handoff for any reply

**Independent Test**: `GET /v1/traces/{trace_id}` returns the review record and 404 for an unknown id

### Tests for User Story 7 ⚠️

- [X] T033 [P] [US7] Write the trace contract test in `tests/test_contract.py`

### Implementation for User Story 7

- [X] T034 [US7] Persist `latency_ms`, `retrieval_scores`, tools, and outcome on each chat in `app/observability/traces.py`
- [X] T035 [US7] Emit one JSON log line per chat without raw tool payloads in `app/observability/traces.py`
- [X] T036 [US7] Return the stored record from `GET /v1/traces/{trace_id}` in `app/main.py`

**Checkpoint**: All user stories should now be independently functional

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T037 [P] Document build, run, tests, orchestration, message flow, and the RAG pipeline in `README.md`
- [X] T038 [P] Package the lexical path in `Dockerfile` and `docker-compose.yml` so `docker compose up --build` serves port 8000 with no API key
- [X] T039 Run the quickstart checks in `specs/001-agent-orchestration/quickstart.md` via `pytest` and a local chat request

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational (Phase 2) - Independently testable through the support tools
- **User Story 3 (P1)**: Can start after Foundational (Phase 2) - Integrates US1 and US2 behind the router and stays testable via `data/evaluation.yaml`
- **User Story 4 (P2)**: Can start after Foundational (Phase 2) - Adds `web_search` without using Getnet passages as evidence
- **User Story 5 (P2)**: Can start after Foundational (Phase 2) - Guardrail runs before specialists
- **User Story 6 (P2)**: Can start after Foundational (Phase 2) - Escalation is a separate agent
- **User Story 7 (P3)**: Can start after Foundational (Phase 2) - Review records are written for every outcome

### Within Each User Story

- Tests (if included) MUST be written and FAIL before implementation
- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- All tests for a user story marked [P] can run in parallel
- Models within a story marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Launch the User Story 1 test and corpus together:
Task: "Write retrieval tests for antecipação and Payment Link in tests/test_retrieval.py"
Task: "Write original corpus summaries with title and url front matter in data/corpus/"
```

---

## Parallel Example: User Story 2

```bash
# Launch fixture and tools together:
Task: "Create the cliente1988 fixture in data/merchants.json"
Task: "Implement get_merchant_account scoped to the request user_id in app/tools/merchant.py"
Task: "Implement get_receivables scoped to the request user_id in app/tools/receivables.py"
Task: "Implement diagnose_terminal in app/tools/terminal.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Add User Stories 4–7 → Test independently → Deploy/Demo
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1
   - Developer B: User Story 2
   - Developer C: User Story 5 and User Story 6
3. Stories complete and integrate independently through `app/orchestration/service.py`

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
