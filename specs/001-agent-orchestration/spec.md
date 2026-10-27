# Feature Specification: Getnet Assist Orchestration

**Feature Branch**: `001-agent-orchestration`

**Created**: 2026-10-24

**Status**: Draft

**Input**: User description: "Build Getnet Assist so a merchant can send one message plus a user identifier and receive a useful answer. A coordinator chooses among product knowledge, account support, a general public lookup, or a human handoff. Product answers stay grounded in public Getnet material. Account answers use only that merchant's data. Unsafe, cross-customer, and unsupported requests are refused. The ten briefing scenarios are the acceptance set, judged by who handled the message and which customer fact was used, not by wording."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask about Getnet products (Priority: P1)

A merchant asks how a Getnet product or policy works and receives an answer
tied to public Getnet material, or a clear statement that the assistant does
not have that fact.

**Why this priority**: Product questions are the majority of the briefing
scenarios and the reason the knowledge role exists.

**Independent Test**: Submit a product question for a known merchant and
confirm the answer cites public Getnet material or admits uncertainty, without
using another merchant's account.

**Acceptance Scenarios**:

1. **Given** merchant `cliente1988`, **When** they ask the difference between
   Get Clássica and Get Smart, **Then** the product specialist answers from
   public Getnet material and names the sources used.
2. **Given** merchant `cliente1988`, **When** they ask whether a bank account
   is required to receive sales via Pix, **Then** the product specialist
   answers from public Getnet material about Pix and does not invent a rule.
3. **Given** merchant `cliente1988`, **When** they ask how receivables advance
   (antecipação) works, **Then** the product specialist answers from public
   Getnet material about antecipação.
4. **Given** merchant `cliente1988`, **When** they ask how many installments a
   crediário sale can be split into, **Then** the product specialist answers
   from public Getnet material about crediário or states that the public
   material does not give a number.
5. **Given** merchant `cliente1988`, **When** they ask whether they can sell
   through WhatsApp using the Payment Link, **Then** the product specialist
   answers from public Getnet material about the payment link.
6. **Given** a product question whose topic is absent from the public
   material, **When** the merchant asks it, **Then** the answer does not
   invent a fee, deadline, or limit and either says so or offers a human
   handoff.

---

### User Story 2 - Resolve the merchant's own account (Priority: P1)

A merchant asks about their sales deposit, their receiving setup, or a card
machine problem and receives an answer based only on their own records, with
a concrete next step.

**Why this priority**: Account and terminal help is the second half of the
brief and must never leak another customer's data.

**Independent Test**: Submit an account question for `cliente1988` and confirm
the answer uses that merchant's receivables, account, or terminal record and
no other merchant's record.

**Acceptance Scenarios**:

1. **Given** merchant `cliente1988` with yesterday's sales on file, **When**
   they ask when that money will be deposited, **Then** account support uses
   their receivables record and states the expected deposit timing from that
   record.
2. **Given** merchant `cliente1988` whose card machine will not connect to the
   internet, **When** they describe that fault, **Then** account support uses
   a terminal diagnosis for that merchant and returns recovery steps.
3. **Given** merchant `cliente1988` whose card machine shows a transaction
   decline, **When** they report that error, **Then** account support uses a
   terminal diagnosis for that merchant and returns decline guidance.
4. **Given** an unknown user identifier, **When** they ask when yesterday's
   sales will be deposited, **Then** the assistant does not invent balances
   and says the account record was not found.

---

### User Story 3 - Direct each message to the right specialist (Priority: P1)

Every accepted message is handled by one primary specialist: product
knowledge, account support, or a general public lookup. The merchant sees one
coherent answer, and a reviewer can see which specialist handled it.

**Why this priority**: The brief is an orchestration challenge. A correct
answer from the wrong kind of specialist fails the evaluation set.

**Independent Test**: Run the ten briefing messages and compare the specialist
and the customer fact used with the evaluation set. Wording is not graded.

**Acceptance Scenarios**:

1. **Given** the ten briefing messages for `cliente1988`, **When** each is
   submitted, **Then** the specialist and the fact used match the evaluation
   set below.
2. **Given** a message that mixes a product topic and an account topic,
   **When** it is submitted, **Then** one primary specialist handles it, chosen
   by the dominant need (the merchant's own money, machine, or identity wins
   over a general product explanation).

Evaluation set (specialist and fact, not wording):

1. Difference between Get Clássica and Get Smart — product knowledge, public
   Getnet material.
2. Weather forecast in Porto Alegre tomorrow — general public lookup, not
   Getnet material.
3. When yesterday's sales money will be deposited — account support,
   receivables for that user.
4. Whether a bank account is required to receive Pix sales — product
   knowledge, public Getnet material.
5. Card machine will not connect to the internet — account support, terminal
   diagnosis for that user.
6. How receivables advance (antecipação) works — product knowledge, public
   Getnet material.
7. Euro exchange rate today — general public lookup, not Getnet material.
8. Card machine showing a transaction decline — account support, terminal
   diagnosis for that user.
9. How many installments crediário allows — product knowledge, public Getnet
   material.
10. Selling through WhatsApp with the Payment Link — product knowledge, public
    Getnet material.

---

### User Story 4 - Answer general questions without pretending they are Getnet (Priority: P2)

A merchant asks for the weather or an exchange rate and receives a general
public answer, clearly separate from Getnet product knowledge.

**Why this priority**: Two briefing scenarios are general questions. They must
not be stuffed into the product corpus or refused as if they were unsafe.

**Independent Test**: Ask for tomorrow's weather in Porto Alegre and today's
euro rate and confirm both are answered as general public lookups.

**Acceptance Scenarios**:

1. **Given** merchant `cliente1988`, **When** they ask for the weather in
   Porto Alegre tomorrow, **Then** the answer comes from a general public
   lookup and does not cite Getnet product material as the source.
2. **Given** merchant `cliente1988`, **When** they ask for today's euro
   exchange rate, **Then** the answer comes from a general public lookup and
   does not cite Getnet product material as the source.

---

### User Story 5 - Refuse unsafe or unsupported requests (Priority: P2)

The assistant refuses prompt manipulation, requests for another customer's
data, and topics it has no specialist for, without answering the forbidden
part.

**Why this priority**: A support assistant that leaks data or follows injected
instructions is not shippable, even if the happy path is correct.

**Independent Test**: Submit an injection, a cross-customer lookup, and an
unsupported topic and confirm each returns a refusal and no account facts.

**Acceptance Scenarios**:

1. **Given** a message that tries to override the assistant's rules, **When**
   it is submitted, **Then** the assistant refuses and does not reveal hidden
   instructions or another customer's data.
2. **Given** merchant `cliente1988`, **When** they ask for another merchant's
   sales or account, **Then** the assistant refuses and returns no record for
   the other merchant.
3. **Given** a topic with no specialist and no general lookup (for example a
   request to move money or change a contract), **When** it is submitted,
   **Then** the assistant says it cannot help with that topic.

---

### User Story 6 - Hand off when the assistant should not guess (Priority: P2)

When the merchant asks for a person, or the assistant cannot answer with
confidence, the merchant receives a handoff reference and the reason.

**Why this priority**: The brief rewards a human path for requests the system
cannot resolve confidently.

**Independent Test**: Ask to speak with a person and confirm the reply
contains a handoff reference and does not invent an account fact.

**Acceptance Scenarios**:

1. **Given** merchant `cliente1988`, **When** they ask to talk to a human,
   **Then** the reply includes a handoff reference and the reason.
2. **Given** a Getnet question with no supporting public material and no
   account record that answers it, **When** it is submitted, **Then** the
   merchant is told the assistant is unsure and is offered a handoff instead
   of a fabricated policy.

---

### User Story 7 - Review how a reply was produced (Priority: P3)

An operator can open one reply and see the path taken: whether it was
refused, which specialist answered, which customer fact or public source was
used, and whether a handoff was created.

**Why this priority**: The brief asks for an evaluation and observability
story. The operator view makes the orchestration auditable without a new
dashboard product.

**Independent Test**: Submit one accepted message and one refusal and confirm
each can be reviewed afterward with specialist, outcome, and sources or
refusal reason.

**Acceptance Scenarios**:

1. **Given** a completed reply, **When** an operator reviews that reply,
   **Then** they see the specialists involved, the outcome, and any sources
   or handoff.
2. **Given** a refusal, **When** an operator reviews it, **Then** they see
   that the request was refused and why, with no customer record attached.

---

### Edge Cases

- An empty or blank message is rejected with a clear prompt to send a
  question, and no specialist runs.
- A missing user identifier is rejected before any account lookup.
- An unknown user identifier on an account question yields "record not found",
  not guessed balances or machine state.
- A product answer with no matching public passage does not state a fee,
  deadline, or installment count.
- Weather and exchange-rate questions never use Getnet product passages as
  their source.
- A request that names another customer returns none of that customer's data,
  even if the caller knows the other identifier.
- A message that is both a product question and an account question keeps a
  single primary specialist.
- If the general public lookup is unavailable, the merchant is told the
  general fact could not be retrieved. The assistant does not replace it with
  a Getnet product answer.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A caller MUST be able to submit one message and one user
  identifier and receive one structured reply.
- **FR-002**: Every reply MUST identify the outcome path: refused, product
  knowledge, account support, general public lookup, or human handoff.
- **FR-003**: A product or policy reply MUST cite the public Getnet material
  it used, or MUST say the material does not support an answer.
- **FR-004**: The assistant MUST NOT invent Getnet fees, settlement deadlines,
  product limits, or eligibility.
- **FR-005**: Account support MUST be able to read the caller's merchant
  profile, the caller's receivables, and a diagnosis for the caller's card
  machine.
- **FR-006**: Every account read MUST be limited to the user identifier on
  the request. Another customer's profile, receivables, or machine state MUST
  NOT appear in the reply or in the review record.
- **FR-007**: The fixture merchant `cliente1988` MUST have receivables for
  yesterday's sales, a receiving setup, and a card machine that can be
  diagnosed for connectivity loss and for a decline.
- **FR-008**: General public lookup MUST be available for weather and exchange
  rates and MUST NOT be used as evidence for Getnet product or policy claims.
- **FR-009**: The assistant MUST refuse instruction override, requests for
  another customer's data, and topics outside product knowledge, account
  support, weather, and exchange rates.
- **FR-010**: A request to speak with a person, and any Getnet question the
  assistant cannot support, MUST return a handoff reference and a reason.
- **FR-011**: Each of the ten briefing messages MUST be classifiable to the
  specialist and fact listed in User Story 3. Grading MUST ignore wording.
- **FR-012**: Every accepted or refused reply MUST be reviewable afterward by
  a reference, including specialists involved, outcome, sources or refusal
  reason, and handoff when one exists.
- **FR-013**: Review records MUST NOT store raw customer payloads. They MAY
  store the user identifier, the specialist path, and source titles.
- **FR-014**: The same ten messages MUST be runnable as a repeatable
  evaluation set that checks specialist and fact, without calling a paid
  language service.
- **FR-015**: A reviewer MUST be able to start the packaged service from the
  documented steps and receive a grounded product answer with no paid language
  service configured.
- **FR-016**: Empty messages and missing user identifiers MUST be rejected
  before a specialist answers.

### Key Entities

- **Chat Request**: The merchant's message and user identifier.
- **Reply**: The answer text, outcome path, confidence, sources, and optional
  handoff.
- **Public Source**: A titled passage from public Getnet material, with its
  public address, used to ground a product answer.
- **Merchant Profile**: The receiving setup for one user identifier, including
  whether Pix receipt is available to that merchant.
- **Receivable**: Yesterday's sales amount and the expected deposit timing for
  one user identifier.
- **Terminal Diagnosis**: The merchant's machine symptom (no internet or
  decline) and the recovery steps for that merchant only.
- **Handoff**: A reference and reason created when a person must take over.
- **Review Record**: The auditable path for one reply, keyed by a reference,
  without raw customer payloads.
- **Evaluation Scenario**: One briefing message plus the expected specialist
  and the expected fact. Wording is not part of the scenario.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 10 briefing messages resolve to the expected specialist and
  fact on a repeatable run (10 of 10).
- **SC-002**: In that same run, 0 replies disclose another customer's profile,
  receivables, or machine state.
- **SC-003**: Every product reply in the evaluation set either names a public
  Getnet source or explicitly says the public material is insufficient. Zero
  product replies invent a fee, deadline, or limit.
- **SC-004**: Both general questions (Porto Alegre weather and the euro rate)
  are answered as general public lookups, and neither cites Getnet product
  material as its source.
- **SC-005**: A reviewer can open the review record for any of the 10 replies
  and see the specialist path in one step.
- **SC-006**: A refusal for injection, cross-customer access, or an
  unsupported topic returns no account facts (0 leaked facts across those
  three checks).
- **SC-007**: A request to speak with a person returns a handoff reference in
  the same reply.
- **SC-008**: A reviewer following only the documented start steps gets a
  grounded answer to "how does antecipação work?" without configuring a paid
  language service.

## Assumptions

- Callers are trusted to pass the merchant's user identifier. Sign-in is out
  of scope for this phase.
- Merchant profiles, receivables, and terminal states are demonstration
  records, not a live Getnet back office. `cliente1988` is the demonstration
  merchant from the brief.
- Public Getnet material is a curated snapshot of getnet.net, including the
  English pages, covering card machines, Pix, antecipação, the payment link,
  crediário, and machine support. The service does not browse the live site
  on each question.
- One message has one primary specialist. Account need outranks a general
  product explanation when both are present.
- General public lookup is limited to weather and foreign-exchange questions
  named by the brief.
- Replies follow the language of the merchant's message. The briefing
  messages are English.
- A production dashboard, live crawl, private Getnet interfaces, login, and
  model fine-tuning are out of scope.
- Operators judge quality with the evaluation set and review records. A
  scheduled live-model grading job is described for later and is not required
  for acceptance.
- Handoff creates a reference for a human operator. It does not page an
  on-call team in this phase.
