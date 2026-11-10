# Arquivos alterados pela spec 002

Lista do que a feature `002-hallucination-detection` mudou no código, no contrato e na constituição. A comparação é o working tree contra o commit `ade3ba3` em `main`. Essas mudanças ainda não estão commitadas.

A spec pede medir se a resposta alucinou com dados que o serviço já tem, gravar afirmações, evidência, checks e veredito no registro de revisão, e expor só o veredito em `GET /v1/traces/{trace_id}/check`. O corpo de `POST /v1/chat` permanece o mesmo.

Nove arquivos existentes foram editados (`+396 / −42`). Três caminhos novos entram com a feature: o módulo do check, a suíte e a pasta da spec.

## Resumo

| Arquivo | Papel da mudança |
| --- | --- |
| `.specify/memory/constitution.md` | Princípio V passa a 1.1.0 e autoriza a rota de check |
| `app/domain/models.py` | Modelos de afirmação, evidência, check e veredito |
| `app/observability/hallucination_check.py` | Arquivo novo. As três regras e a confiança |
| `app/observability/traces.py` | O store não muda. O docstring registra o que agora é gravado |
| `app/agents/knowledge.py` | O produto emite claims e entrega as passagens recuperadas |
| `app/agents/support.py` | O suporte emite uma claim por campo, sem gravar o valor |
| `app/orchestration/service.py` | `_finish` chama `evaluate` depois de montar o `Reply` |
| `app/rag/retriever.py` | `name` em `bm25` e `chroma` |
| `app/main.py` | Rota `GET /v1/traces/{trace_id}/check` |
| `specs/001-agent-orchestration/contracts/chat.openapi.yaml` | A rota e os esquemas novos no contrato |
| `tests/test_hallucination.py` | Arquivo novo. Pass e fail de cada check |
| `specs/002-hallucination-detection/` | A spec e o checklist de qualidade |

O modelo `Reply` não ganhou campo. O guardrail não foi alterado.

## Constituição

Arquivo: `.specify/memory/constitution.md`.

O cabeçalho de impacto troca `1.0.0` por `1.1.0` e marca o princípio V como expandido. O texto do princípio, que listava só as duas rotas originais, passa a incluir a leitura do check e os cinco campos do registro:

```markdown
The core MUST expose only `POST /v1/chat`, `GET /v1/traces/{trace_id}`, and
`GET /v1/traces/{trace_id}/check`. The review record for a reply MAY include
`claimed_statements`, `evidence`, `check_results`, `verdict`, and
`verdict_confidence`, and every reply MUST be markable with those check
results. The check route returns only the verdict, its confidence, and the
check results.
```

A justificativa deixa de falar só em limite de superfície e passa a dizer que o check lê o rastro que o serviço já guarda. O rodapé fecha a emenda:

```markdown
**Version**: 1.1.0 | **Ratified**: 2026-10-24 | **Last Amended**: 2026-11-07
```

## Modelos

Arquivo: `app/domain/models.py`.

O docstring do módulo deixa de dizer "duas rotas públicas" e passa a nomear chat, registro de revisão e leitura do check. Quatro literais novos delimitam o vocabulário:

```python
ClaimKind = Literal["product", "support"]
CheckName = Literal["anchor", "tool_payload", "structured_output"]
CheckStatus = Literal["pass", "fail", "not_applicable"]
VerdictName = Literal["hallucinated", "verified", "unverified"]
RetrieverName = Literal["bm25", "chroma"]
```

Quatro modelos entram entre `Reply` e `ReviewRecord`. `ClaimedStatement` guarda a afirmação: tipo, texto, citações e nomes de campo. No suporte, `text` fica vazio e `fields` traz só o nome. `SourceEvidence` grava título, URL, retriever e nota. `ToolEvidence` grava ferramenta, nomes de campo e `matched`. `CheckResult` é o par nome e status. `extra` continua proibido.

`ReviewRecord` ganha cinco campos obrigatórios no fim, sem alterar os que já existiam:

```python
claimed_statements: list[ClaimedStatement]
evidence: list[SourceEvidence | ToolEvidence]
check_results: list[CheckResult]
verdict: VerdictName
verdict_confidence: float = Field(ge=0, le=1)
```

`CheckResponse` é o corpo da rota nova. Só `trace_id`, `verdict`, `verdict_confidence` e `check_results`. A classe `Reply` não foi tocada.

## Check de alucinação

Arquivo novo: `app/observability/hallucination_check.py`.

`RetrievedPassage` e `StatedField` existem só na memória da requisição. `StatedField.value` é o valor afirmado para comparar com o retorno da ferramenta. Esse valor não é campo de `ReviewRecord`. `HallucinationReport` é o que `_finish` grava.

`evaluate` percorre as claims, monta a evidência e devolve sempre os três resultados nesta ordem: `anchor`, `tool_payload`, `structured_output`. A barra reusa `MIN_SCORE` (`0.15`) e define `KEEP_RATIO = 0.94`.

`_anchor` só olha claims de produto. Sem claim de produto, o status é `not_applicable`. Cada URL citada precisa existir na recuperação da pergunta e ter nota de pelo menos `0.15` e de pelo menos 94% da maior nota. A comparação usa uma folga de `1e-12`. URL ausente marca `anchor_missing`, que depois força confiança `1`.

`_tool_payload` vale quando há claim de suporte ou quando uma das três ferramentas de conta rodou (`get_merchant_account`, `get_receivables`, `diagnose_terminal`). Cada campo afirmado precisa existir no retorno e ser igual ao valor em `StatedField`. Campo ausente ou valor diferente falha na hora.

`_structured` fica `not_applicable` para consulta geral, recusa e handoff sem claim. Numa resposta factual, lista vazia falha. Citação de produto fora das `sources` falha. Citação de suporte para ferramenta que não foi chamada falha.

`_verdict` aplica a regra da spec:

- nenhum check aplicável: `unverified`, confiança `0`;
- qualquer falha aplicável: `hallucinated`. Confiança `1` se a falha é citação ausente, lista vazia ou campo divergente. Se a única falha é nota abaixo da barra, a confiança é a distância até a barra, limitada a `0.01`–`1`;
- todos os aplicáveis passam: `verified`. A confiança é a menor nota citada, ou `1` quando a prova foi só de ferramenta.

`_source_evidence` só grava passagem cuja URL estava na recuperação. `_tool_evidence` grava o nome do campo e `matched`, sem o valor.

## Rastro

Arquivo: `app/observability/traces.py`.

A classe `TraceStore` não mudou. `put` continua gravando o `ReviewRecord` inteiro num dicionário do processo e escrevendo uma linha JSON no logger `getnet.assist`. O que mudou é o docstring, para deixar explícito que o registro agora inclui afirmações, evidência, checks e veredito, e que valores de ferramenta não fazem parte desse registro:

```python
"""In-memory review records and one JSON log line per chat.

The stored record includes claimed statements, evidence, check results, and
the verdict. Tool values are not part of that record. The map is empty after
a process restart.
"""
```

Como o modelo passou a carregar esses campos, a mesma linha JSON os inclui. `amount_brl` pode aparecer como nome em `fields`. O valor numérico não é campo do modelo.

## Agente de conhecimento

Arquivo: `app/agents/knowledge.py`.

O prompt de produto deixa de pedir "mencione os títulos" e passa a exigir JSON com `answer` e `claims`. Cada citação tem de ser uma URL copiada da mensagem:

```python
Return JSON only, with keys "answer" and "claims".
"answer" is the prose reply. "claims" is a list of objects with "text" and "citations".
Each citation is a passage URL copied from the user message. Do not cite any other URL.
```

`KnowledgeResult` ganha três campos, com default vazio para a consulta geral, que não emite claim:

```python
claims: list[ClaimedStatement] = field(default_factory=list)
retrieved: list[RetrievedPassage] = field(default_factory=list)
retriever_name: str = "bm25"
```

Em `answer_product`, todas as passagens recuperadas viram `RetrievedPassage`, inclusive as que ficam abaixo da barra. O nome do retriever vem de `BM25Retriever.name` ou `ChromaRetriever.name`. Quando não há passagem forte, o retorno de handoff leva essa lista e o nome, e a lista de claims continua vazia.

O trecho que escolhe o texto e as claims substitui o caminho antigo, que usava a prosa do modelo ou colava as passagens sem afirmação estruturada:

```python
generated = self._llm.answer(PRODUCT_SYSTEM, _prompt(message, strong))
parsed = _claims_from_model(generated) if generated else None
if generated is None:
    answer = "Based on public Getnet material:\n\n" + "\n\n".join(hit.text.strip() for hit in strong)
    claims = [
        ClaimedStatement(kind="product", text=hit.text.strip() or hit.title, citations=[hit.url])
        for hit in strong
    ]
elif parsed is None:
    answer = generated
    claims = []
else:
    answer, claims = parsed
    if not answer:
        answer = "Based on public Getnet material:\n\n" + "\n\n".join(hit.text.strip() for hit in strong)
```

Sem modelo, há uma claim por passagem mantida. Com JSON válido, as claims são as do modelo. Com prosa, a lista fica vazia: o serviço não varre o texto para inventar citação. O `KnowledgeResult` de sucesso passa `claims`, `retrieved` e `retriever_name` adiante. `answer_general` não foi alterado e segue sem claims.

`_claims_from_model` é função nova. Aceita o JSON puro ou um objeto JSON embutido na resposta. Exige `claims` como lista de objetos com `text` string e `citations` lista de strings não vazias. Qualquer formato fora disso devolve `None`.

## Agente de suporte

Arquivo: `app/agents/support.py`.

`SupportResult` ganha `claims`, `stated` e `payload`. Os três métodos (`_receivables`, `_profile`, `_terminal`) deixam de construir `SupportResult` direto. O texto da resposta é o mesmo. A diferença é que cada retorno chama `_result` com o nome da ferramenta, o dicionário da ferramenta e a lista dos campos que a frase afirmou.

Os nomes passados em cada caminho:

| Método | Registro ausente | Registro encontrado |
| --- | --- | --- |
| `_receivables` | `status` | `status`, `amount_brl`, `expected_deposit` |
| `_profile` | `status` | `machine_model`, `pix_enabled`, `receiving_setup` |
| `_terminal` | `status` | `machine_model`, `symptom`, `steps` |

`_result` é o trecho novo. Uma claim por campo, citando a ferramenta e sem texto. O valor fica em `StatedField` e no `payload`, os dois só em memória:

```python
def _result(
    self,
    *,
    answer: str,
    confidence: float,
    tool: str,
    record: dict[str, Any],
    names: list[str],
) -> SupportResult:
    claims = [
        ClaimedStatement(kind="support", citations=[tool], fields=[name])
        for name in names
    ]
    stated = [StatedField(tool=tool, field=name, value=record[name]) for name in names]
    return SupportResult(
        answer=answer,
        confidence=confidence,
        tools=[tool],
        claims=claims,
        stated=stated,
        payload=record,
    )
```

`sales_label` continua no retorno de recebíveis e no escopo da spec, mas a frase atual não o afirma, então não entra em `names`.

## Orquestração

Arquivo: `app/orchestration/service.py`.

O ramo de suporte, que antes terminava só com texto, confiança e ferramentas, passa a entregar as claims e o payload em memória:

```python
return self._finish(
    ...
    tools=result.tools,
    claims=result.claims,
    stated=result.stated,
    payloads={result.tools[0]: result.payload} if result.tools else {},
    started=started,
)
```

O ramo de produto faz o equivalente com `claims`, `retrieved` e `retriever`. O handoff por `insufficient_sources` continua chamando `_escalate` sem claims. Recusa, pedido de pessoa e consulta geral também chegam a `_finish` sem esses argumentos. O default vazio faz os três checks ficarem `not_applicable`.

`_finish` monta o `Reply` primeiro, com os mesmos campos de antes, e só então chama `evaluate`. O veredito entra no `ReviewRecord` e não volta para o `Reply`:

```python
reply = Reply(
    trace_id=trace_id,
    answer=answer,
    route=route,
    sources=sources or [],
    confidence=confidence,
    handoff=handoff,
    tools_used=tools or [],
)
report = evaluate(
    intent=intent,
    outcome=outcome,
    claims=claims,
    stated=stated,
    payloads=payloads,
    sources=sources,
    retrieved=retrieved,
    retriever=retriever,
    tools=tools,
)
self.traces.put(
    ReviewRecord(
        ...
        claimed_statements=report.claimed_statements,
        evidence=report.evidence,
        check_results=report.check_results,
        verdict=report.verdict,
        verdict_confidence=report.verdict_confidence,
    )
)
return reply
```

A assinatura de `_finish` ganhou `claims`, `stated`, `payloads`, `retrieved` e `retriever`, todos opcionais.

## Retriever

Arquivo: `app/rag/retriever.py`.

Dois atributos de classe, para a evidência registrar qual índice produziu a nota. A busca não mudou.

```python
class BM25Retriever:
    name = "bm25"

class ChromaRetriever:
    name = "chroma"
```

## HTTP

Arquivo: `app/main.py`.

A validação de UUID e o 404 saem de `read_trace` para `load_trace`, usada pelas duas leituras. A rota nova projeta só o veredito. `POST /v1/chat` continua devolvendo `Reply`:

```python
def load_trace(trace_id: str) -> ReviewRecord:
    try:
        UUID(trace_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Unknown trace") from exc
    record = service.traces.get(trace_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown trace")
    return record

@app.get("/v1/traces/{trace_id}/check", response_model=CheckResponse)
def read_check(trace_id: str) -> CheckResponse:
    record = load_trace(trace_id)
    return CheckResponse(
        trace_id=record.trace_id,
        verdict=record.verdict,
        verdict_confidence=record.verdict_confidence,
        check_results=record.check_results,
    )

@app.get("/v1/traces/{trace_id}", response_model=ReviewRecord)
def read_trace(trace_id: str) -> ReviewRecord:
    return load_trace(trace_id)
```

UUID inválido e rastro desconhecido respondem `404` com `{"detail": "Unknown trace"}`, sem corpo de veredito.

## Contrato OpenAPI

Arquivo: `specs/001-agent-orchestration/contracts/chat.openapi.yaml`.

A descrição do documento deixa de dizer "duas rotas" e passa a nomear chat, registro e check. O path novo é `GET /v1/traces/{trace_id}/check`, operação `getTraceCheck`, com `200` em `CheckResponse` e `404` em `ErrorBody`.

`ReviewRecord.required` ganha `claimed_statements`, `evidence`, `check_results`, `verdict` e `verdict_confidence`. Os esquemas acrescentados são `ClaimedStatement`, `SourceEvidence`, `ToolEvidence`, `CheckResult` e `CheckResponse`, com `additionalProperties: false` e os mesmos enums dos modelos Python. `evidence` é `oneOf` entre fonte recuperada e comparação de ferramenta.

## Testes

Arquivo novo: `tests/test_hallucination.py`. Roda com modelo falso e sem rede. Não julga o texto da resposta.

| Teste | O que o trecho fixa |
| --- | --- |
| `test_anchor_pass_records_source_and_score` | Âncora passa e a evidência traz título, URL, `bm25` e nota |
| `test_anchor_fail_when_score_is_under_the_keep_bar` | Nota 0,5 contra topo 0,8 falha só a âncora |
| `test_tool_payload_pass_and_terminal_fields_match` | `symptom` e `steps` iguais ao retorno |
| `test_tool_payload_fail_does_not_store_the_amount` | Depósito divergente falha e o valor não entra no JSON |
| `test_structured_output_fails_when_the_citation_was_not_used` | URL fora das sources, ou ferramenta citada sem chamada |
| `test_empty_claim_list_on_a_factual_reply_fails_structured_output` | Prosa factual sem claims é `hallucinated` |
| `test_not_found_status_passes_and_a_stated_balance_fails` | `status=not_found` passa. Afirmar depósito para usuário ausente falha |
| `test_account_field_mismatch_fails` | `machine_model` diferente falha |
| `test_check_route_is_slim_and_the_chat_reply_is_unchanged` | O check não devolve a resposta. O chat não ganha veredito |
| `test_receivables_trace_omits_the_amount` | O rastro de `cliente1988` não contém o valor nem o nome legal |
| `test_refusal_handoff_and_general_questions_are_unverified` | Recusa, pedido de pessoa, tempo e câmbio |
| `test_unknown_and_malformed_check_ids_are_not_found` | UUID desconhecido e id malformado devolvem 404 |

## Spec

Pasta nova: `specs/002-hallucination-detection/`.

`spec.md` é o contrato da feature, status aceito, com as quatro histórias, os requisitos FR-001 a FR-014 e os critérios SC-001 a SC-008. `checklists/requirements.md` é o checklist de qualidade da spec, marcado. A tradução desse contrato está em `spec-002-hallucination-detection-pt.md`. O desenho da implementação está em `SPEC-002-TECNICO.md`.
