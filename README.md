# Getnet Assist

Multi-agent assistant for a Getnet merchant. One HTTP service accepts a message and a `user_id`, chooses a specialist, and returns a grounded answer or a handoff.

The ten briefing scenarios are graded by specialist and tool, not by wording. They live in `data/evaluation.yaml`.

A developer who is new to the repository should start with [MANUAL.md](MANUAL.md).

## Build, configure, and run

Requires Python 3.12 in Docker, or Python 3.10+ locally. No API key is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Optional model access, for phrasing and for the Chroma index:

```bash
cp .env.example .env
# set OPENAI_API_KEY, and OPENAI_BASE_URL if you use a compatible gateway
```

`OPENAI_MODEL` defaults to `gpt-4o-mini`. With a key, the router may accept a JSON intent from the model, and the knowledge role may phrase an answer from the retrieved passages only. If the key is empty, or the `openai` package is not installed, the intent table and the extractive answer are used.

Packaged run:

```bash
docker compose up --build
```

The image listens on port 8000. Leave `OPENAI_API_KEY` empty for the offline check.

Chat:

```bash
curl -s localhost:8000/v1/chat \
  -H 'content-type: application/json' \
  -d '{"message":"How does receivables advance (antecipação) work with Getnet?","user_id":"cliente1988"}'
```

Then read the review record:

```bash
curl -s localhost:8000/v1/traces/<trace_id>
```

The only routes are `POST /v1/chat` and `GET /v1/traces/{trace_id}`.

## Tests

```bash
pytest
```

The suite uses a fake LLM and a fake web lookup. It does not call OpenAI, Open-Meteo, or Frankfurter. Contract, routing, retrieval, guardrail, and the ten-scenario evaluation set are included. `GETNET_INGEST` is forced off so the suite stays offline and reads the corpus already on disk.

### End-to-end integration test plan

This is the live path, from the HTTP entry point through every agent. The automated suite above is the same `POST /v1/chat` stack with fakes. A release check repeats it against a running server.

1. Ingest. `python -m app.rag.ingest` downloads `https://www.getnet.net/` and `https://www.getnet.net/en` and writes `data/corpus/getnet-root.md` and `data/corpus/getnet-en.md`. Confirm both files exist and that each front-matter `url` is one of those two addresses.
2. Boot. `docker compose up --build` with `GETNET_INGEST=1` (the compose default). Startup downloads those two pages again, then builds the index. If the download fails, the process logs a warning and serves the files already in the image.
3. Drive `POST /v1/chat` with `{"message", "user_id"}`, then `GET /v1/traces/{trace_id}` for the same `trace_id`. Check one case per specialist:

| Case | Message | Route | What to assert |
| --- | --- | --- | --- |
| Product | Difference between Get Clássica and Get Smart | guardrail, router, knowledge | `sources` cite a Getnet URL. No support tool. |
| Account | When yesterday's sales are deposited | guardrail, router, support | Tool `get_receivables`. Trace has no amount. |
| Terminal | Card machine will not connect | guardrail, router, support | Tool `diagnose_terminal`. |
| General | Weather in Porto Alegre, and the euro rate | guardrail, router, knowledge | Tool `web_search`. `sources` is empty. |
| Guardrail | Instruction override, or another customer's data | guardrail | `outcome` `refused`. Route does not continue. No tool. |
| Handoff | Ask for a person | guardrail, router, escalation | `outcome` `handoff`. Reference matches `ESC-` plus 8 characters. |

4. Repeat the ten messages in `data/evaluation.yaml` against `localhost:8000`. Each reply's route, tools, and sources must match that file. The trace for every reply must carry intent, outcome, and latency.

## Orchestration

One process. Agents pass an in-memory handoff (`trace_id`, intent, confidence, payload). There is no queue.

```text
POST /v1/chat
  -> GuardrailAgent
  -> RouterAgent
  -> KnowledgeAgent | SupportAgent | EscalationAgent
  -> Reply + ReviewRecord
```

| Agent | Role |
| --- | --- |
| Guardrail | Blocks an empty message, instruction override, and a request for another customer's data. |
| Router | Picks `product_knowledge`, `account_support`, `general_web`, `human_handoff`, or `out_of_scope`. A valid model intent overrides the keyword table. Otherwise the table covers the briefing scenarios. Account need is decided before a general product explanation. |
| Knowledge | Retrieves public Getnet passages, or calls `web_search` for weather and exchange rates. |
| Support | Calls `get_merchant_account`, `get_receivables`, and `diagnose_terminal` with the request `user_id` only. |
| Escalation | Returns a reference `ESC-` plus 8 characters when the merchant asks for a person, confidence is below 0.45, or the corpus does not support the answer. |

`cliente1988` is a fixture in `data/merchants.json`, not a live Getnet account. Yesterday's sales are scheduled for the next business day. The card machine on file is a Get Smart.

## Message workflow

1. The caller sends `message` and `user_id`. A `user_id` outside `^[A-Za-z0-9_-]+$` returns 422.
2. The guardrail stops injection and cross-customer reads. The route is `["guardrail"]` and no tool runs.
3. The router selects one intent.
4. Product questions retrieve the corpus. The reply cites titles and URLs, or becomes a handoff with reason `insufficient_sources`.
5. Account questions call one support tool. An unknown `user_id` is told that no record exists. Amounts are not copied into the review record.
6. Weather and the euro rate call `web_search`. Those replies have an empty `sources` list. If the lookup fails, the reply says the general fact is unavailable.
7. A human request returns `outcome=handoff` and a reference.
8. Every reply is stored under `trace_id` and written as one JSON log line without the tool payload.

## RAG pipeline

Ingestion downloads the two URLs named in the brief and stores the visible page text:

```bash
python -m app.rag.ingest
```

`app/rag/ingest.py` fetches `https://www.getnet.net/` and `https://www.getnet.net/en`, strips scripts and styles, and writes `data/corpus/getnet-root.md` and `data/corpus/getnet-en.md` with `title` and `url` front matter. Those two files keep the requested URL even when the site redirects both to the same English home page. With `GETNET_INGEST=1` (the default for `docker compose` and for `Settings.from_env`), the service runs that download again at startup before it builds the index. `GETNET_INGEST=0` skips the download and uses the files already on disk.

The other corpus files are additional public sources, kept as short summaries so Brazilian product rules stay in the index without copying those pages. Fees that the pages say can change are not treated as permanent numbers.

Additional sources:

- https://site.getnet.com.br/maquininha/get-classica/
- https://site.getnet.com.br/maquininha/get-smart/
- https://site.getnet.com.br/pagamentos-digitais/
- https://site.getnet.com.br/wp-content/uploads/2025/09/Manul-GetSmart.pdf
- https://site.getnet.com.br/get-ajuda-antecipacao-de-venda/como-antecipar-sua-vendas-pelo-app/
- https://site.getnet.com.br/crediario/
- https://site.getnet.com.br/link-de-pagamento/

Storage is the Markdown files in the image. Retrieval is BM25 (`rank-bm25`). A score is `raw / (raw + 1)`. A top hit below `0.15`, or no hit within 94% of that top score, is not used as evidence. If nothing remains, the reply is a handoff instead of a guessed policy.

When `OPENAI_API_KEY` is set and both `openai` and `chromadb` import, startup embeds the same documents into a Chroma collection under `data/.chroma` with `text-embedding-3-small` and prefers that index. Any failure falls back to BM25.

Generation without a key returns the retrieved passages and their titles. Generation with a key sends only those passages to the model, with instructions to avoid facts that are not in them. Citations on the reply are the retrieved documents either way.

`web_search` is separate. Weather uses Open-Meteo for Porto Alegre (`-30.0346`, `-51.2177`). The euro rate uses Frankfurter (`EUR` to `BRL`). Neither result is stored in the Getnet index.

## LLM tools

- `get_merchant_account(user_id)` reads the fixture profile.
- `get_receivables(user_id)` reads yesterday's sales and the expected deposit.
- `diagnose_terminal(user_id, symptom)` returns connectivity or decline steps for that merchant. `symptom` is `connectivity` or `decline`.
- `web_search` answers weather and exchange-rate questions.

The model does not choose tool arguments from the message. The support role passes the request `user_id`.

## Evaluation and observability

`pytest` runs `data/evaluation.yaml` and checks intent, route, and tools. A nightly job that scores a live model is a production step, not part of this service.

Each chat writes a review record: route, intent, tool names, source titles and URLs, retrieval scores, outcome, confidence, handoff, and latency. `GET /v1/traces/{trace_id}` returns it. Logs are JSON on stdout. They omit raw customer payloads.

In production, the same fields can be exported with OpenTelemetry. Alert when the evaluation-set route accuracy drops, and when handoff volume or guardrail refusals jump. This repository does not ship a dashboard.

## Out of scope

Live CRM, private Getnet APIs, crawling the site on each question, login, fine-tuning, and a metrics dashboard.
