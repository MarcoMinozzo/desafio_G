# Getnet Assist developer manual

This manual explains the whole repository for a developer who did not build it. [README.md](README.md) is the short runbook. This file is the map of why the system exists, how one message moves through it, and where to change behavior safely.

## 1. What this project is

Getnet Assist is a small customer-support service for a Getnet merchant. The caller sends one message and one user identifier, and may send a session id to continue the same thread. The service decides which specialist should answer, then returns one JSON reply. The reply does not include the hallucination verdict. That verdict is a separate read.

It was built for the challenge in [AI_Hardcore_Engineer_Multi-Agent.md](AI_Hardcore_Engineer_Multi-Agent.md). The challenge asks for at least three cooperating agents, a `POST` endpoint, Docker, tests, and a written account of the design. This repository implements five roles inside one process:

1. A guardrail that refuses unsafe requests.
2. A router that picks one intent, or support followed by knowledge when the message asks for both the merchant's account and a public product fact.
3. A knowledge agent for public Getnet facts and for general lookups such as weather.
4. A support agent for the caller's own account and card machine.
5. An escalation agent that opens a human handoff.

After the reply text is fixed, three mechanical checks score whether the claims are anchored. A metrics snapshot counts outcomes and verdicts for the process.

There is no login, no live Getnet back office, and no second container. Merchant data is a fixture. Product answers come from a curated local corpus, not from browsing the website on each question. The caller is trusted to send the right `user_id`. Session memory is isolated by that id, not by a sign-in.

## 2. How the repository is organized

```text
AI_Hardcore_Engineer_Multi-Agent.md   original challenge
MANUAL.md                             this document
README.md                             build, run, test
INVENTARIO.md                         file-by-file map of the running code
app/                                  the running service
data/corpus/                          public Getnet pages used by search
data/merchants.json                   fixture for user cliente1988
data/evaluation.yaml                  the ten official scenarios
tests/                                pytest suite, no network and no paid model
specs/001-agent-orchestration/        orchestration spec, plan, tasks, OpenAPI
specs/002-hallucination-detection/    hallucination spec and its checklist
.specify/                             Spec Kit project memory and templates
Dockerfile                            one image
docker-compose.yml                    one service on port 8000
```

Read the code in this order:

1. [app/main.py](app/main.py) shows the four HTTP routes and how the app is assembled.
2. [app/orchestration/service.py](app/orchestration/service.py) is the workflow. Every accepted or refused chat goes through `ChatService.handle`.
3. [app/agents/](app/agents) holds one file per role.
4. [app/observability/](app/observability) holds the trace store, the three checks, and the metrics counters.
5. [app/rag/](app/rag) loads and searches the corpus.
6. [app/tools/](app/tools) holds account tools and the general web lookup.
7. [data/evaluation.yaml](data/evaluation.yaml) is the behavior the ten briefing tests treat as correct.

`specs/` and `.specify/` explain how the work was specified. They are not imported by the running service. The constitution in [.specify/memory/constitution.md](.specify/memory/constitution.md) is version 1.2.0. It still requires grounded product answers, data isolated by `user_id`, tests that run without a live model, and one container. It allows the chat route, the review record, the check read, and the metrics read. Session memory must stay keyed by `user_id` and must not keep tool values.

## 3. Two kinds of documents

The Spec Kit flow produced the design before the code:

| Artifact | What a new developer uses it for |
| --- | --- |
| `.specify/memory/constitution.md` | Rules that later changes must still satisfy |
| `specs/001-agent-orchestration/spec.md` | What the merchant can do, without naming libraries |
| `specs/001-agent-orchestration/plan.md` | Stack and file layout |
| `specs/001-agent-orchestration/data-model.md` | Fields and allowed values from the first feature |
| `specs/001-agent-orchestration/contracts/chat.openapi.yaml` | HTTP contract, including the check, the session, and metrics |
| `specs/001-agent-orchestration/tasks.md` | The work breakdown that was implemented for orchestration |
| `specs/001-agent-orchestration/quickstart.md` | The checks used to validate a run |
| `specs/002-hallucination-detection/spec.md` | The three checks, the verdict, and the slim check read |

If the code and the spec disagree, fix the code to match the spec, or amend the spec and the constitution together. Do not add an HTTP route, a database, or a dashboard without changing those documents first.

## 4. Runtime shape

One Python process. FastAPI exposes the service. Agents do not call each other over the network. `ChatService` calls them in order and passes an in-memory object.

```text
caller
  POST /v1/chat { message, user_id, session_id? }
       |
       v
  GuardrailAgent
       | allowed
       v
  RouterAgent  ---- intent + detail
       |
       +-- human_handoff or confidence < 0.45 --> EscalationAgent
       +-- out_of_scope ------------------------> refusal
       +-- general_web -------------------------> KnowledgeAgent.answer_general
       +-- account_support ---------------------> SupportAgent
       +-- account_support and product ---------> SupportAgent, then KnowledgeAgent
       +-- product_knowledge -------------------> KnowledgeAgent.answer_product
                                                      | no usable passage
                                                      v
                                                 EscalationAgent
       |
       v
  Reply to the caller          (no verdict on this body)
  evaluate                      (anchor, tool payload, structured output)
  ReviewRecord in memory and one JSON log line
  SessionStore.remember         (same user_id + session_id)
  MetricsStore.record
```

There are two different objects named handoff. Do not mix them up.

- `app.orchestration.handoff.Handoff` is the internal message: `trace_id`, `intent`, `confidence`, and a `payload` dict. Agents read the merchant text from `payload["message"]` and the caller from `payload["user_id"]`.
- `app.domain.models.Handoff` is the receipt returned to the caller: `reference` like `ESC-A1B2C3D4` and a `reason`.

`create_app` in [app/main.py](app/main.py) builds a new service on each call. Tests pass a fake language model and a fake web lookup into that function. The module-level `app` object is what Uvicorn serves, using environment variables.

OpenAPI, Swagger, and ReDoc are turned off. The constitution allows `POST /v1/chat`, `GET /v1/traces/{trace_id}`, `GET /v1/traces/{trace_id}/check`, and `GET /v1/metrics`.

## 5. The HTTP contract

### `POST /v1/chat`

Request:

```json
{
  "message": "When will the money from yesterday's sales be deposited?",
  "user_id": "cliente1988"
}
```

`message` must be 1 to 4000 characters after it is accepted by the schema. A blank string, a missing field, or a `user_id` outside `^[A-Za-z0-9_-]+$` (length 1 to 64) returns HTTP 422 with `{"detail": "Invalid request"}`. A message that is only spaces has a non-zero length, so it reaches the guardrail and comes back as HTTP 200 with a refusal.

A well-formed request always returns HTTP 200, including refusals and handoffs. The body is:

```json
{
  "trace_id": "uuid",
  "answer": "text",
  "route": ["guardrail", "router", "knowledge"],
  "sources": [{"title": "Receivables advance (antecipacao)", "url": "https://..."}],
  "confidence": 0.86,
  "handoff": null,
  "tools_used": [],
  "session_id": "uuid"
}
```

`route` is the ordered list of roles that ran. Allowed names are `guardrail`, `router`, `knowledge`, `support`, and `escalation`. `guardrail` is always first. A message that asks about the merchant's own machine and a product fact runs `support` and then `knowledge`.

`session_id` comes back on every reply. Send it on the next call, with the same `user_id`, to continue that thread. Omit it to start a new one. Another `user_id` does not see the thread. The stored turn is the merchant's words, the intent, and the detail. Tool values are not stored.

`sources` cites public Getnet pages. It is empty for account answers, weather, exchange rates, refusals, and handoffs.

`tools_used` is one of `get_merchant_account`, `get_receivables`, `diagnose_terminal`, and `web_search`. Product answers use no tool. The model never chooses the user id that a tool receives.

`handoff` is `null` or:

```json
{"reference": "ESC-A1B2C3D4", "reason": "human_requested"}
```

Reasons are `human_requested`, `low_confidence`, and `insufficient_sources`.

### `GET /v1/traces/{trace_id}`

Returns the review record for that chat. An unknown or non-UUID id returns HTTP 404.

The record repeats the route, intent, tool names, sources, retrieval scores, outcome, confidence, handoff, latency, and `session_id`. It also carries `claimed_statements`, `evidence`, `check_results`, `verdict`, and `verdict_confidence`. It does not store the answer text, the sale amount, the merchant legal name, account numbers, or the raw tool return. A support field name such as `amount_brl` may appear in `fields`, because the evidence records which fields were compared. Outcome is `answered`, `refused`, or `handoff`. Intent is `product_knowledge`, `account_support`, `general_web`, `human_handoff`, `out_of_scope`, or `refused`. On a mixed turn the intent stays `account_support` and the route lists both `support` and `knowledge`.

The same record is written as one JSON line on stdout by the logger named `getnet.assist`. The store is an in-memory dict in [app/observability/traces.py](app/observability/traces.py). It is empty after a process restart.

### `GET /v1/traces/{trace_id}/check`

Returns only `trace_id`, `verdict`, `verdict_confidence`, and `check_results`. The verdict is `verified`, `hallucinated`, or `unverified`. Each check is `anchor`, `tool_payload`, or `structured_output`, and each status is `pass`, `fail`, or `not_applicable`. An unknown or non-UUID id returns HTTP 404 with `{"detail": "Unknown trace"}` and no verdict body.

`verdict_confidence` is not the `confidence` on the chat reply. It is 0 when nothing applied. It is 1 when a citation is missing, the claim list is empty, or a tool field disagrees. When the only failure is a retrieval score under the keep bar, it is the distance from that bar, clamped to 0.01 through 1. When the reply is verified from passages, it is the lowest cited score. When it is verified from tools alone, it is 1.

The check does not change the merchant's answer, does not refuse a reply the guardrail already accepted, and does not run the guardrail again.

### `GET /v1/metrics`

Returns counts of replies, outcomes, and verdicts, the age in days of the oldest corpus file, and the alert names that are active. There is no `user_id` and no tool value. After 10 replies the process logs a warning when the hallucinated share is above 0.3 or the handoff share is above 0.5. A corpus file older than 30 days adds `corpus_stale`. The logger name is `getnet.assist.metrics`. The counters live in the process and are empty after a restart.

## 6. What each agent does

### Guardrail

File: [app/agents/guardrail.py](app/agents/guardrail.py).

It runs before the router and does not call a model. It refuses:

- a blank or whitespace message
- instruction override, such as "ignore previous instructions" or "reveal the system prompt"
- a request for another customer, detected by phrases such as "another customer" or by a `cliente` plus digits id that is not the request `user_id`

On a refusal the route is only `["guardrail"]`, no tool runs, and no specialist sees the message.

### Router

File: [app/agents/router.py](app/agents/router.py).

It returns one intent, a `detail` string, and sometimes a second step. The detail tells the next agent which tool or lookup to use.

Human handoff, weather, and exchange rate still win alone, in that order. Account phrases and product phrases are then detected separately. If both are present, `steps` is `account_support` then `product_knowledge`, and that sequence is kept even when a model returns a single intent. If only one signal is present and `classify` returns one of the five allowed intents, the model wins and the table still supplies `detail` when it agrees. If the model is absent, fails, or returns anything else, the table decides. Tests use `FakeLLM` to prove the single-intent override. The default install uses `NullLLM`, so the table is the path you will see.

A follow-up with no specialist phrase continues the previous turn when that turn, for the same `user_id` and `session_id`, was product, account, or a general lookup. The retrieval query becomes the stored topic, not the short fragment. Confidence for that continuation is 0.62, above the handoff floor. A different `user_id` does not see the topic.

Accents are stripped before matching, so "antecipação" matches the token `antecip`.

| If the text contains | Intent | Detail |
| --- | --- | --- |
| talk to a human, talk to a person, speak to a person, human operator | `human_handoff` | `human` |
| weather, forecast | `general_web` | `weather` |
| euro, exchange rate | `general_web` | `fx` |
| decline, declined | `account_support` | `decline` |
| connect, internet, wifi, wi-fi | `account_support` | `connectivity` |
| deposited, deposit, yesterday | `account_support` | `receivables` |
| receiving setup, my account, machine model, which machine | `account_support` | `profile` |
| classica, get smart, smart, pix, bank account, antecip, crediario, installment, whatsapp, payment link | `product_knowledge` | `product` |
| getnet, and no account phrase | `product_knowledge` | `product` at confidence 0.55 |
| anything else | `out_of_scope` | `unsupported` |

A message that contains only an account phrase stays on support. "When will yesterday's sales be deposited?" does not contain a product token, so knowledge does not run. "Do I need a bank account to receive sales via Pix?" does not contain "deposit" or "yesterday", so it stays a product question. "My card machine won't connect" plus "antecipação" runs both.

A router confidence below `0.45` becomes a handoff with reason `low_confidence`. The current table does not emit a score that low. The branch exists for a future model score.

### Knowledge

File: [app/agents/knowledge.py](app/agents/knowledge.py).

`answer_product` searches the corpus. It keeps hits with a normalized score of at least `0.15` and within 94 percent of the best hit. Every retrieved hit, including the ones below that bar, is kept as a `RetrievedPassage` so the anchor check can see the score. If nothing qualifies and this is the only step, the service opens a handoff with reason `insufficient_sources` and does not invent a fee, a deadline, or a limit. If support already answered in the same turn, the product part says the public material does not support the rest and the account answer stays.

Without an API key, the answer is the text of the kept passages, prefixed with "Based on public Getnet material", and there is one product claim per kept passage. The citation is that passage URL. With a key, the model is asked for JSON with `answer` and `claims`. Valid JSON becomes the claim list. Prose leaves the claim list empty. The service does not scan the prose for citations. An empty claim list on a factual product reply fails `structured_output`. Citations on the reply are still the retrieved documents. The retriever name on the evidence is `bm25` or `chroma`.

`answer_general` does not search the corpus. It calls `web_search` and returns an empty `sources` list. Weather uses Open-Meteo for Porto Alegre, latitude `-30.0346` and longitude `-51.2177`, and reads tomorrow from the daily forecast. The euro rate uses Frankfurter, EUR against BRL, and follows redirects. If the HTTP call fails, the reply says the general lookup is unavailable and does not substitute a Getnet page.

### Support

File: [app/agents/support.py](app/agents/support.py).

The agent receives `user_id` from the request payload. It never parses another id out of the message. The `detail` from the router selects the tool:

| Detail | Tool | What the answer uses |
| --- | --- | --- |
| `receivables` | `get_receivables` | Yesterday's amount and expected deposit |
| `connectivity` | `diagnose_terminal` with symptom `connectivity` | Steps stored for that merchant |
| `decline` | `diagnose_terminal` with symptom `decline` | Steps stored for that merchant |
| `profile` | `get_merchant_account` | Machine model, Pix flag, receiving setup |

An unknown user gets a not-found sentence. The tool does not fall back to `cliente1988`.

Each path emits one support claim per field the sentence stated. The citation is the tool name. The claim text is empty. The compared value lives only on `StatedField` for the duration of the request, next to the tool dict. Neither is copied onto the review record. A missing record states `status` only. A found receivables record states `status`, `amount_brl`, and `expected_deposit`. A found profile states `machine_model`, `pix_enabled`, and `receiving_setup`. A found terminal states `machine_model`, `symptom`, and `steps`. `sales_label` is on the tool return and is not claimed, because the sentence does not state it.

The three tools live in [app/tools/merchant.py](app/tools/merchant.py), [app/tools/receivables.py](app/tools/receivables.py), and [app/tools/terminal.py](app/tools/terminal.py). They all read the dict loaded from [data/merchants.json](data/merchants.json). That file is demonstration data. `cliente1988` has a Get Smart, Pix enabled, yesterday's sales of BRL 1840.50 scheduled for the next business day, and short connectivity and decline playbooks. The legal name is in the file and is not returned by the tools or written to the trace.

### Escalation

File: [app/agents/escalation.py](app/agents/escalation.py).

It creates `ESC-` plus eight uppercase hex characters. It does not notify a person. The reference is the handoff for this phase.

## 7. The knowledge corpus

`data/corpus/*.md` is the only Getnet knowledge the service searches. Each file has front matter:

```yaml
---
title: Payment Link and WhatsApp
url: https://site.getnet.com.br/link-de-pagamento/
---
```

[app/rag/corpus.py](app/rag/corpus.py) uses the file name without `.md` as the document id, then the title, URL, and body. `getnet-root.md` and `getnet-en.md` are the visible text of the two brief URLs, written by `python -m app.rag.ingest`. The other bodies are original English summaries of public Brazilian pages. Promotional rates that the sites say can change are not copied in as permanent numbers.

| File | Question it is meant to answer |
| --- | --- |
| `get-classica.md` | What Get Classica is, and how it differs from Get Smart |
| `get-smart.md` | What Get Smart adds, and who it is for |
| `pix.md` | Whether a bank account is required to receive Pix sales |
| `antecipacao.md` | How receivables advance works |
| `crediario.md` | How many installments crediario can offer |
| `payment-link.md` | Whether a Payment Link can be sent through WhatsApp |
| `terminal-help.md` | What the public manual says about connectivity |
| `getnet-root.md` | Downloaded text of https://www.getnet.net/ |
| `getnet-en.md` | Downloaded text of https://www.getnet.net/en |

The URLs in front matter are the citations. Paths on `site.getnet.com.br` stay as published addresses even though the summary text is English.

### How search ranks a passage

[app/rag/retriever.py](app/rag/retriever.py) tokenizes text by stripping accents, lowercasing, and dropping a short stopword list. `BM25Okapi` from `rank-bm25` scores the query. A raw score `s` becomes `s / (s + 1)` when `s` is positive, and `0` otherwise. The knowledge agent then applies the `0.15` floor and the 94 percent cutoff described above.

That cutoff is why a Pix question returns the Pix page and not every document that mentions Getnet. If you add a document that repeats another topic's words, check the top hit with a small script or with `tests/test_retrieval.py` before merging.

When `OPENAI_API_KEY` is set and both the `openai` and `chromadb` packages import, `build_retriever` embeds the same documents into a Chroma collection at `data/.chroma` with `text-embedding-3-small` and uses that index instead. Any failure, including a missing package, falls back to BM25. The default install and the Docker image do not include those extra packages. Install them with:

```bash
pip install -e ".[llm]"
```

Do not crawl the live site at startup. Add a new summary file, keep the front matter, and describe only what that page actually states.

## 8. The ten scenarios

[data/evaluation.yaml](data/evaluation.yaml) is the acceptance set from the challenge. [tests/test_evaluation.py](tests/test_evaluation.py) posts each row and checks intent, the specialist named in `route_contains`, the tools named in `tools_contain`, and whether Getnet sources are required. It does not compare answer wording.

| Scenario | Specialist | Tool | Sources |
| --- | --- | --- | --- |
| Difference between Get Classica and Get Smart | knowledge | none | yes |
| Weather in Porto Alegre | knowledge | `web_search` | no |
| When yesterday's sales will be deposited | support | `get_receivables` | no |
| Bank account for Pix sales | knowledge | none | yes |
| Card machine will not connect | support | `diagnose_terminal` | no |
| How receivables advance works | knowledge | none | yes |
| Euro exchange rate | knowledge | `web_search` | no |
| Transaction decline | support | `diagnose_terminal` | no |
| Crediario installment count | knowledge | none | yes |
| Payment Link on WhatsApp | knowledge | none | yes |

The scenario messages keep the product spellings from the challenge, including accents. Matching code folds accents, so the corpus can stay in plain English.

## 9. Configuration

[app/config.py](app/config.py) reads the environment when `Settings.from_env` is called.

| Variable | Default | Effect |
| --- | --- | --- |
| `OPENAI_API_KEY` | empty | Empty selects the keyword router, extractive answers, and BM25 |
| `OPENAI_BASE_URL` | empty | Optional base URL for an OpenAI-compatible gateway |
| `OPENAI_MODEL` | `gpt-4o-mini` | Chat model used only when a key is set |
| `GETNET_INGEST` | `1` | `0` skips the startup download and uses the Markdown already on disk |

Corpus and merchant paths are derived from the repository root, two levels above `app/config.py`. Docker copies `app/` and `data/` into `/app`, and the same relative layout works.

`.env.example` lists the variables. The process does not load a `.env` file by itself. Export the variables, or pass them through Compose.

## 10. Run and test

Local:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Python 3.10 or newer works for local tests. The image uses Python 3.12.

Packaged:

```bash
docker compose up --build
```

The Compose service publishes port 8000 and passes through `OPENAI_API_KEY`. Leave the key empty to confirm the offline path.

Tests live in `tests/`. `conftest.py` builds the app with an empty API key and `FakeWebSearch`, so pytest does not call Open-Meteo, Frankfurter, or a model.

| File | What it locks |
| --- | --- |
| `test_contract.py` | Response shape, including `session_id`, 422 for a bad user id, 404 for an unknown trace, no amount in the trace |
| `test_guardrail.py` | Blank text, injection, another customer, an unsupported topic |
| `test_orchestration.py` | Deposit scope, unknown user, terminal tools, profile tool, human handoff, fake model override |
| `test_retrieval.py` | Antecipacao and Payment Link documents win their queries offline |
| `test_evaluation.py` | All ten scenarios, each still one specialist |
| `test_ingest.py` | HTML extraction and the two named Getnet URLs |
| `test_hallucination.py` | Pass and fail for each check, the slim check read, no stored sale amount |
| `test_improvements.py` | Mixed support-then-knowledge, session follow-up, isolation across `user_id`, metrics and alerts |

When you change routing or the corpus, run `pytest` before trusting a manual curl. A curl checks one wording. The evaluation file checks the set.

## 11. Where to make a change

Add a public Getnet fact. Add or edit a Markdown file in `data/corpus/` with `title` and `url`. State only what the page states. Run the retrieval tests and a chat for that question. Confirm the top source is the new file and that unrelated questions did not start citing it.

Add a fixture merchant. Add an object to `data/merchants.json` keyed by `user_id`, with `machine_model`, `pix_enabled`, `receiving_setup`, `receivable`, and `terminal` steps. Do not make tools search by a name found in the message.

Add a route for a new English phrase. Add the phrase to `_account` or `_product` in [app/agents/router.py](app/agents/router.py). Human, weather, and exchange rate stay exclusive and ahead of those two detectors. A phrase that belongs to both will run both specialists. Add a row to `data/evaluation.yaml` if the phrase is a new acceptance case, and extend `tests/test_evaluation.py` only if the assertion shape changes. The existing test already loops over the YAML.

Change the reply sentence for an account tool. Edit the matching method in `SupportAgent` and the field names passed to `_result`. Keep the not-found branch. The amount may be compared in memory. Do not put it on `ReviewRecord`, on the check body, or on the session turn.

Turn on a real model. Set `OPENAI_API_KEY`. The router will prefer a valid JSON intent unless the keyword table already found both account and product. The knowledge agent will use JSON claims when the model returns them, and an empty claim list when it returns prose. The keyword table remains the fallback. Do not let the model pick `user_id` or call tools with arguments taken from the user text.

Change an alert threshold. Edit `MIN_SAMPLE`, `HALLUCINATED_RATIO`, `HANDOFF_RATIO`, or `CORPUS_MAX_AGE_DAYS` in [app/observability/metrics.py](app/observability/metrics.py). The snapshot stays aggregate. Do not add a `user_id` or a tool value to it.

Add a production trace backend. Replace the body of `TraceStore.put` and `TraceStore.get`. Keep the `ReviewRecord` fields, including the verdict. Do not log tool payloads. Session and metrics are separate stores. They are also process-local today.

## 12. Invariants

These are the mistakes that break the design even if a single demo still looks fine.

- A product answer with no retrieved passage must be a handoff or an explicit gap, never a guessed fee or installment count. On a mixed turn the account answer stays and the product gap is stated.
- Support tools receive the request `user_id` and no other identifier.
- Weather and exchange rates must not cite a Getnet URL, and they stay `unverified` rather than `hallucinated`.
- The review record, the check body, the metrics snapshot, the session turn, and the log line must not contain sale amounts, legal names, account numbers, or raw tool results.
- A session id is not proof of identity. The same id under another `user_id` must not load the original thread.
- A failed check must not rewrite or refuse the reply the merchant already received.
- New HTTP routes are out of scope until the constitution is amended. Version 1.2.0 already allows the check read and the metrics read.
- Tests must pass with no API key and no network.

## 13. What this repository deliberately does not do

It does not call private Getnet APIs, crawl the site on each question, authenticate the caller, fine-tune a model, or render a dashboard. `user_id` is trusted because the caller sends it. The handoff reference is not delivered to an operator queue. OpenTelemetry export is not implemented. The process does log a JSON warning on `getnet.assist.metrics` when the hallucinated share, the handoff share, or the corpus age crosses the threshold in [app/observability/metrics.py](app/observability/metrics.py).

The trace store, the session store, and the metrics counters are process-local. Running more than one worker loses the record if the follow-up `GET` hits a different process. The Compose file runs one process, which matches that limit. A corpus file older than 30 days raises `corpus_stale`. The service does not refresh the summary files on its own. Only `https://www.getnet.net/` and `https://www.getnet.net/en` are downloaded again at startup, and only when `GETNET_INGEST` is not `0`.
