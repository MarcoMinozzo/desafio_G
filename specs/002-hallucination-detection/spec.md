# Feature Specification: Hallucination Detection

**Feature Branch**: `002-hallucination-detection`

**Created**: 2026-11-07

**Status**: Accepted

**Input**: User description: "Measure whether a Getnet Assist reply hallucinated, using only data the service already has for that reply: retrieved passages and their scores, the support-tool return, and the claims the answering agent emitted. Extend the review record with the claims, the evidence, the check results, and a verdict. Expose those check results on a separate read. Do not invent new evidence, do not store a second copy of customer data, and do not change the merchant's answer."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See whether a product claim is anchored (Priority: P1)

A reviewer opens one product reply and sees each claim the knowledge
specialist asserted, the public passage that was supposed to support it, and
whether that passage was actually retrieved strongly enough to keep.

**Why this priority**: Invented fees, deadlines, and limits are the failure
the constitution already forbids. This is the check that makes that failure
visible.

**Independent Test**: Submit one product question whose answer cites a kept
passage, and one product answer that cites a passage below the keep bar.
Confirm the first is a pass and the second is a fail, without calling a paid
language service.

**Acceptance Scenarios**:

1. **Given** a product reply that states a fact and cites a passage the
   retriever kept for that question, **When** the reviewer reads the check,
   **Then** the anchor check passes and the evidence names that passage's
   title, public address, retriever (`bm25` or `chroma`), and score.
2. **Given** a product reply that states a fact and cites a retrieved passage
   whose score is below the keep bar, **When** the reviewer reads the check,
   **Then** the anchor check fails.
3. **Given** a product reply that admits the public material is insufficient
   and states no product fact, **When** the reviewer reads the check,
   **Then** the anchor check is not applicable and the reply is not marked
   hallucinated for lacking a citation.

---

### User Story 2 - See whether an account claim matches the tool (Priority: P1)

A reviewer opens one account or terminal reply and sees whether every field
the support specialist stated matches the tool return for that same
`user_id`. The comparison uses the tool return the service already computed.
The stored record does not keep the raw return.

**Why this priority**: A support answer that disagrees with the merchant's
own record is a hallucination even when the route and the tool name are
correct.

**Independent Test**: Submit one receivables question whose stated deposit
timing equals the tool return, and one whose stated timing does not. Confirm
pass and fail. Confirm the stored record contains the field name and the
result, and does not contain the amount.

**Acceptance Scenarios**:

1. **Given** merchant `cliente1988` and a receivables answer whose
   `expected_deposit` equals `get_receivables` for that user, **When** the
   reviewer reads the check, **Then** the tool-payload check passes.
2. **Given** the same merchant and a receivables answer whose
   `expected_deposit` differs from `get_receivables`, **When** the reviewer
   reads the check, **Then** the tool-payload check fails.
3. **Given** a terminal answer that states `symptom` and `steps` equal to
   `diagnose_terminal` for that user and that symptom, **When** the reviewer
   reads the check, **Then** the tool-payload check passes.
4. **Given** an account answer that states `machine_model`, `pix_enabled`,
   or `receiving_setup` differently from `get_merchant_account` for that
   user, **When** the reviewer reads the check, **Then** the tool-payload
   check fails.
5. **Given** any failing or passing tool-payload check, **When** the review
   record is stored, **Then** it does not contain `amount_brl`, a legal name,
   or an account number. The amount may be compared in memory and then
   discarded.

---

### User Story 3 - Reject a citation that was never retrieved (Priority: P1)

The answering agent emits claims as structured citations, not as unchecked
prose. A citation that is not in the sources or tools of this reply fails,
even if the sentence sounds plausible.

**Why this priority**: The anchor check and the tool check are meaningless if
the agent can cite something the service did not use.

**Independent Test**: Feed one claim list whose citation urls are all in the
reply's sources, and one claim list that cites a url the reply did not use.
Confirm pass and fail with a fake model. No prose similarity is graded.

**Acceptance Scenarios**:

1. **Given** a product answer whose every claim cites a url present in that
   reply's sources, **When** the check runs, **Then** the structured-output
   check passes.
2. **Given** a product answer that states a claim citing a url absent from
   that reply's sources, **When** the check runs, **Then** the
   structured-output check fails.
3. **Given** a support answer whose every claim cites a tool name that was
   actually invoked for that reply, **When** the check runs, **Then** the
   structured-output check passes.
4. **Given** a support answer that cites `get_receivables` when that tool was
   not invoked, **When** the check runs, **Then** the structured-output check
   fails.
5. **Given** a product or support answer that contains factual prose but an
   empty claim list, **When** the check runs, **Then** the structured-output
   check fails. The service does not invent claims by reading the prose.

---

### User Story 4 - Read the verdict without the rest of the reply (Priority: P2)

A reviewer who already has a `trace_id` can ask for the hallucination result
alone: the verdict, how sure that verdict is, and pass or fail for each
check.

**Why this priority**: The full review record is the audit of the reply. The
check read exists so a grader can score hallucination without parsing the
answer, the sources, or the tool path.

**Independent Test**: Complete one checked reply, read the check route, and
confirm the body has only the verdict fields. Read the full review record and
confirm the claims and evidence are still there.

**Acceptance Scenarios**:

1. **Given** a completed reply, **When** the reviewer gets
   `/v1/traces/{trace_id}/check`, **Then** the body contains `trace_id`,
   `verdict`, `verdict_confidence`, and `check_results`, and no answer text,
   sources, claims, evidence, or tool values.
2. **Given** the same reply, **When** the reviewer gets
   `/v1/traces/{trace_id}`, **Then** the review record includes
   `claimed_statements`, `evidence`, `check_results`, `verdict`, and
   `verdict_confidence` in addition to the fields it already has.
3. **Given** a `trace_id` that is not a UUID or that was never stored,
   **When** the reviewer gets the check route, **Then** the response is not
   found and no record body is returned.
4. **Given** the merchant's chat reply, **When** it is returned, **Then** its
   body is unchanged by this feature. The check is not added to the chat
   response.

---

### Edge Cases

- A refusal states no product or account fact. All three checks are not
  applicable. The verdict is `unverified` and `verdict_confidence` is 0.
- A human handoff that states no product or account fact is `unverified` the
  same way. A handoff that still states a product or account fact is checked
  like any other claim.
- Weather and exchange-rate replies are `unverified`. The service does not
  keep a retrieved Getnet passage or a support-tool return for them, so none
  of the three checks apply. They are not marked `hallucinated` for having
  empty sources.
- An unknown user on an account question, answered as "record not found" with
  a claim whose `status` is `not_found` and that states no balance, passes
  the tool-payload check. A claim that states a deposit timing or an amount
  for that unknown user fails it.
- One failing claim fails the reply. Later passing claims do not clear it.
- A check that does not apply does not fail the reply and does not lower a
  passing verdict.
- BM25 and Chroma use the same rules. The evidence records which one produced
  the score. The keep bar does not change between them.
- After a process restart the check cannot be read, because the review record
  was only in memory. That is the current trace store, not a new failure.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every product or support reply that states a fact MUST emit a
  claim list before the review record is stored. Each claim MUST name the
  assertion and its citations. Product citations are source urls. Support
  citations are tool names. The service MUST NOT derive claims by scanning
  answer prose.
- **FR-002**: When no paid model is configured, the product path MUST emit one
  claim per passage it kept, citing that passage, and the support path MUST
  emit one claim per field it stated, citing the tool it called. The same
  three checks MUST run. Tests MUST use this path and a fake model.
- **FR-003**: The anchor check MUST apply only to product claims. It passes
  only when every such claim cites a source that was retrieved for that
  question and whose score meets the keep bar the product answer already
  uses: score at least 0.15, and score at least 94 percent of the top score
  on that question. Otherwise it fails. It is not applicable when the reply
  has no product claim.
- **FR-004**: The tool-payload check MUST apply only when a support tool ran
  or a support claim was emitted. It passes only when every stated field
  equals the tool return for the request `user_id`. The fields in scope are
  `machine_model`, `pix_enabled`, and `receiving_setup` on
  `get_merchant_account`; `status`, `sales_label`, `amount_brl`, and
  `expected_deposit` on `get_receivables`; `status`, `symptom`,
  `machine_model`, and `steps` on `diagnose_terminal`. A stated field the
  tool did not return fails. The check is not applicable when no support tool
  ran and no support claim was emitted.
- **FR-005**: The structured-output check MUST apply to every product or
  support reply that is expected to state a fact. It passes only when the
  claim list is non-empty and every citation is in this reply's sources
  (product) or in this reply's invoked tools (support). An empty claim list
  on such a reply fails. The check is not applicable for a refusal, a
  fact-free handoff, and a general public lookup.
- **FR-006**: Each check result MUST be exactly one of `pass`, `fail`, or
  `not_applicable`.
- **FR-007**: The verdict MUST be `hallucinated` when any applicable check
  failed, `verified` when at least one check applied and every applicable
  check passed, and `unverified` when no check applied.
- **FR-008**: `verdict_confidence` MUST be a number from 0 to 1, separate
  from the reply's existing confidence. It MUST be 0 when the verdict is
  `unverified`. It MUST be 1 when the verdict is `hallucinated` because a
  citation is missing, the claim list is empty, or a tool field disagrees.
  It MUST be the distance from the keep bar down to the cited score, clamped
  to the range 0.01 through 1, when the only failure is a score under the
  bar. It MUST be the lowest cited retrieval score when the verdict is
  `verified` and a passage was cited, and 1 when `verified` on tool evidence
  alone.
- **FR-009**: The review record for every reply MUST gain
  `claimed_statements`, `evidence`, `check_results`, `verdict`, and
  `verdict_confidence`. Existing review fields stay. The chat reply body
  MUST NOT gain these fields.
- **FR-010**: Product evidence MUST record the cited title, public address,
  retriever name (`bm25` or `chroma`), and score. Support evidence MUST
  record the tool name, the field names compared, and whether they matched.
  Support evidence MUST NOT record field values. `amount_brl`, legal names,
  and account numbers MUST NOT be stored on the review record, in the check
  response, or on the log line.
- **FR-011**: A failed check MUST set that check to `fail` and the verdict to
  `hallucinated`. It MUST NOT change the merchant's answer, MUST NOT refuse a
  reply that the guardrail already accepted, and MUST NOT start a second
  guardrail pass.
- **FR-012**: `GET /v1/traces/{trace_id}/check` MUST return only `trace_id`,
  `verdict`, `verdict_confidence`, and `check_results` for a stored reply,
  and MUST return not found for an unknown or non-UUID `trace_id` without a
  record body. This is the only new route. Constitution Principle V, version
  1.1.0, amended 2026-11-07, already allows this route and the hallucination
  fields on the review record. No other route is added. No further
  constitution amendment is required for this feature.
- **FR-013**: Check results MUST be stored in the same in-memory review
  record as the rest of the trace and MUST be written on the same single JSON
  log line, under the same redaction rules. They MUST disappear on process
  restart. A durable store is not part of this feature.
- **FR-014**: The automated suite under `tests/` MUST cover a pass and a fail
  for the anchor check, the tool-payload check, and the structured-output
  check, plus the slim check response and the absence of `amount_brl` on a
  stored receivables check. The suite MUST run with a fake model and without
  network access. It MUST NOT grade answer wording.

### Key Entities

- **Claimed statement**: One assertion the answering agent emitted. A product
  statement has the assertion text and one or more source urls. A support
  statement has the tool name and the field names it stated, with no field
  values stored.
- **Evidence**: The backing already on hand for one claim. Either a retrieved
  public source (title, address, retriever, score) or a tool comparison (tool
  name, field names, matched or not). Never a raw customer payload.
- **Check result**: One of the three checks (`anchor`, `tool_payload`,
  `structured_output`) and its status (`pass`, `fail`, `not_applicable`).
- **Verdict**: `hallucinated`, `verified`, or `unverified`, plus
  `verdict_confidence` from 0 to 1.
- **Check response**: The slim read of one trace: identifier, verdict,
  confidence, and the three check results.
- **Review record**: The existing per-reply record, extended with the claim
  list, the evidence, the check results, and the verdict. Still process-local.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the repeatable suite, the anchor pass case passes and the
  anchor fail case fails (2 of 2).
- **SC-002**: In the repeatable suite, the tool-payload pass case passes and
  the tool-payload fail case fails (2 of 2), and the stored fail case
  contains 0 copies of the sales amount.
- **SC-003**: In the repeatable suite, the structured-output pass case passes
  and the structured-output fail case fails (2 of 2).
- **SC-004**: Across those six cases, the verdict matches the rule: any
  applicable failure is `hallucinated`, and all applicable passes are
  `verified` (6 of 6).
- **SC-005**: A reviewer can read the check result for a completed reply in
  one request, and that response contains none of the answer text (0 answer
  fields).
- **SC-006**: The merchant's chat response for those cases is the same shape
  as before this feature (0 check fields added to the chat body).
- **SC-007**: Refusal, fact-free handoff, and the two general questions
  (weather and euro rate) are `unverified` rather than `hallucinated` (4 of
  4).
- **SC-008**: The suite that proves SC-001 through SC-007 runs with no paid
  language service and no network.

## Assumptions

- The keep bar is the one the product answer already applies: a passage is
  citable only when its score is at least 0.15 and at least 94 percent of the
  top score for that question. This feature does not choose a new threshold.
- "The model emits claims" means a structured claim list on the product and
  support paths. When the model is absent, the deterministic fallback in
  FR-002 emits that same list from the passages it kept or the fields it
  stated. Prose is never parsed for claims.
- Support comparisons are exact equality on the named fields. Paraphrase
  matching is not used.
- `verdict_confidence` does not replace the reply confidence the merchant
  already receives.
- Callers of the check route are the same operators who can already read a
  review record by `trace_id`. No new sign-in is added.
- Constitution Principle II still holds. Comparing `amount_brl` in memory is
  allowed. Writing it down is not.
- Constitution Principle V was amended on 2026-11-07 to version 1.1.0. It
  allows `GET /v1/traces/{trace_id}/check` and the hallucination fields on
  the review record. That amendment is done.

## Out of Scope

- Durable storage for traces or check results. Restart behavior stays as it
  is today.
- Changing, blocking, or rewriting the merchant's answer when a check fails.
- A dashboard, an alert, or a second guardrail pass.
- Checking weather or exchange-rate answers. The service keeps no passage
  score and no support payload for them.
- New retrieval, new models, paraphrase grading, and any hallucination metric
  that needs data this reply does not already have.
