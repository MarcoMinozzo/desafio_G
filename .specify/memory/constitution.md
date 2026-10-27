<!--
Sync Impact Report
- Version change: unratified template → 1.0.0
- Modified principles: placeholders replaced by the five Getnet Assist principles
- Added sections: Delivery Constraints, Quality Gates
- Removed sections: none (template slots filled)
- Follow-up TODOs: none
-->

# Getnet Assist Constitution

## Core Principles

### I. Grounded Answers

Product and policy answers MUST be grounded in a retrieved Getnet source or
MUST state uncertainty. The system MUST NOT invent fees, deadlines, product
limits, or eligibility. A knowledge answer without a retrieved passage MUST
become an explicit uncertainty or a human handoff.

Rationale: evaluators and customers must be able to trace every Getnet claim
to a public source.

### II. Customer Data Isolation

Support tools MUST scope every read to the `user_id` on the request. The
system MUST NOT return another customer's account, receivables, or terminal
state. Logs MUST omit raw customer payloads and MUST carry only the `user_id`
and a `trace_id`.

Rationale: the support agent holds merchant data; cross-customer leakage is a
hard failure even in the fixture store.

### III. Orchestration Testable Without a Live Model

The router, guardrail, tools, and retrieval MUST be exercisable with a fake
LLM and without network access. Tests MUST assert route, tool, and `user_id`
scope. Tests MUST NOT assert free-form model prose.

Rationale: the core solution has to stay reliable when no API key or credit
is available.

### IV. One Container

The core service MUST build and run as a single container with `docker compose
up`. Agents communicate by an in-process typed handoff. The lexical index MUST
work with no embedding key so the image answers product questions offline.

Rationale: the submission is judged by a standard Docker run, not by a
multi-service platform.

### V. No Extra Surface

The core MUST expose only `POST /v1/chat` and `GET /v1/traces/{trace_id}`.
Work outside that contract — live CRM, private Getnet APIs, runtime crawl,
login, fine-tuning, and a dashboard — is out of scope until the constitution
is amended.

Rationale: screen time for the core is capped, and extra surface competes
with the orchestration the brief asks for.

## Delivery Constraints

- Python 3.12, FastAPI, and an OpenAI-compatible LLM client.
- Public Getnet pages are the knowledge source, stored as a curated local
  corpus. Embeddings and Chroma are optional and activate only when
  `OPENAI_API_KEY` is set. BM25 is the default retrieval path.
- Web search is allowed only for general questions (weather, exchange rates)
  and MUST NOT be used to invent Getnet product facts.
- At least three agent types are required: Router, Knowledge, and Customer
  Support. Guardrail and Escalation are part of this delivery because they
  are small and named in the approved design.
- Customer Support MUST expose at least two tools. This delivery uses
  `get_merchant_account`, `get_receivables`, and `diagnose_terminal`.

## Quality Gates

- `POST /v1/chat` contract tests run through the HTTP stack.
- The ten briefing scenarios are an evaluation dataset of expected route and
  tool, not expected wording.
- Retrieval tests hit the local corpus for antecipação and Payment Link
  without network.
- Guardrail tests cover prompt injection, cross-customer access, and
  unsupported topics.
- A trace record exists for every accepted or refused chat, with agent, tool,
  latency, and retrieval score when retrieval ran.
- README documents build, run, tests, orchestration, message flow, and the
  RAG pipeline from ingestion to generation.

## Governance

This constitution supersedes ad-hoc practice for Getnet Assist. Amendments
require a version bump, a dated note in this file, and a check that specs and
tests still match the changed principle.

- MAJOR: remove or redefine a principle.
- MINOR: add a principle or expand a constraint.
- PATCH: wording that does not change a rule.

Reviews MUST verify grounded answers, `user_id` isolation, fake-LLM tests,
single-container run, and the allowed HTTP surface. Complexity beyond the
in-process handoff MUST be justified against Principle V.

**Version**: 1.0.0 | **Ratified**: 2026-10-24 | **Last Amended**: 2026-10-24
