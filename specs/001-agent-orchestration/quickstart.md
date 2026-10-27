# Quickstart: Getnet Assist Orchestration

Validation guide for the feature in [spec.md](./spec.md). Contracts live in
[contracts/chat.openapi.yaml](./contracts/chat.openapi.yaml). Entities live in
[data-model.md](./data-model.md).

## Prerequisites

- Python 3.12
- Docker, for the packaged run
- No API key is required for the lexical path

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Tests

```bash
pytest
```

Expected:

- Contract checks accept the chat body and reject a bad `user_id`.
- The ten rows in `data/evaluation.yaml` match intent, route, and tools.
- Retrieval for antecipação and Payment Link returns those corpus documents
  with no network.
- Injection, a second customer identifier, and an unsupported topic are
  refused with no account facts.
- A human request returns a handoff reference matching `ESC-[A-Z0-9]{8}`.

## Local run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Product question (grounded, no key):

```bash
curl -s localhost:8000/v1/chat \
  -H 'content-type: application/json' \
  -d '{"message":"How does receivables advance (antecipação) work with Getnet?","user_id":"cliente1988"}'
```

Expected: `route` contains `knowledge`, `sources` is non-empty, `handoff` is
null.

Account question:

```bash
curl -s localhost:8000/v1/chat \
  -H 'content-type: application/json' \
  -d '{"message":"When will the money from yesterday'\''s sales be deposited?","user_id":"cliente1988"}'
```

Expected: `route` contains `support`, `tools_used` contains `get_receivables`.

Then open the review record:

```bash
curl -s localhost:8000/v1/traces/<trace_id>
```

Expected: `intent` is `account_support` and the body has no amount field.

## Packaged run

```bash
docker compose up --build
```

Repeat the antecipação curl against port 8000. Expected outcome matches the
local product question. Do not set `OPENAI_API_KEY` for this check.
