# Data Model: Getnet Assist Orchestration

## ChatRequest

- `message`: string, required, trimmed length 1–4000.
- `user_id`: string, required, length 1–64, pattern `^[A-Za-z0-9_-]+$`.
- Relationship: one request produces one `Reply` and one `ReviewRecord`.

## Reply

- `trace_id`: UUID string, required.
- `answer`: string, required, non-empty.
- `route`: ordered list of agent names. Allowed names: `guardrail`, `router`, `knowledge`, `support`, `escalation`. At least `guardrail`.
- `sources`: list of `PublicSource`. Empty when the answer is not grounded in Getnet material.
- `confidence`: number from 0 to 1 inclusive.
- `handoff`: `Handoff` or null.
- `tools_used`: list of tool names, may be empty. Allowed names: `get_merchant_account`, `get_receivables`, `diagnose_terminal`, `web_search`.

## PublicSource

- `title`: string, required.
- `url`: absolute http(s) URL, required.
- Relationship: belongs to a corpus document and may be copied onto a `Reply`.

## CorpusDocument

- `id`: slug, required.
- `title`: string, required.
- `url`: absolute URL, required.
- `body`: original summary text, required.
- Relationship: split into passages for retrieval. Not exposed as its own endpoint.

## MerchantProfile

- `user_id`: string, required, unique.
- `legal_name`: string, required.
- `machine_model`: string, required.
- `pix_enabled`: boolean, required.
- `receiving_setup`: string, required.
- Relationship: one profile per user. Tools return it only for the request `user_id`.

## Receivable

- `user_id`: string, required.
- `sales_label`: string, required (fixture value `yesterday`).
- `amount_brl`: number, required, greater than or equal to 0.
- `expected_deposit`: string, required.
- `status`: `scheduled` or `not_found`.
- Relationship: at most one current receivable per merchant in this phase.

## TerminalDiagnosis

- `user_id`: string, required.
- `symptom`: `connectivity` or `decline`.
- `machine_model`: string, required.
- `steps`: list of strings, at least one.
- Relationship: derived for the request user. Unknown user yields `status=not_found` and empty steps.

## Handoff

- `reference`: string, required, pattern `ESC-[A-Z0-9]{8}`.
- `reason`: string, required, one of `human_requested`, `low_confidence`, `insufficient_sources`.

## ReviewRecord

- `trace_id`: UUID, required.
- `user_id`: string, required.
- `route`: same allowed names as `Reply.route`.
- `intent`: `product_knowledge`, `account_support`, `general_web`, `human_handoff`, `out_of_scope`, or `refused`.
- `tools`: tool names only.
- `sources`: titles and URLs only.
- `retrieval_scores`: list of numbers, empty if retrieval did not run.
- `outcome`: `answered`, `refused`, or `handoff`.
- `confidence`: number from 0 to 1.
- `handoff`: `Handoff` or null.
- `latency_ms`: integer, greater than or equal to 0.
- Constraint: MUST NOT include merchant legal name, amounts, account numbers, or raw tool payloads.

## EvaluationScenario

- `id`: string, required.
- `message`: string, required.
- `user_id`: string, required.
- `intent`: one of the router intents.
- `route_contains`: agent name that must appear.
- `tools_contain`: list of tool names that must appear (empty when none).
- `sources_required`: boolean.
- Constraint: wording of `answer` is not an expected field.

## State transitions

1. Request arrives and is validated. Invalid `user_id` or empty `message` ends as `outcome=refused` from `guardrail` only.
2. Guardrail allows the message or sets `intent=refused` and stops.
3. Router sets one intent.
4. `product_knowledge` retrieves passages. Sufficient score goes to `answered` with sources. Insufficient score goes to `handoff`.
5. `account_support` calls one or more tools scoped to `user_id`. A not-found tool result stays `answered` and states that the record is missing. It does not escalate into another user's data.
6. `general_web` calls `web_search`. Success is `answered` with empty Getnet sources. Failure is `answered` with an unavailable statement, still with empty Getnet sources.
7. `human_handoff` and low-confidence knowledge end as `outcome=handoff`.
8. `out_of_scope` ends as `outcome=refused`.
