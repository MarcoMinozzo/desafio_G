# SPEC 002 — Detecção de alucinação

Documento técnico da feature `002-hallucination-detection` no Getnet Assist.
Descreve o que foi implementado. A spec de origem está em
`specs/002-hallucination-detection/spec.md`. O checklist de qualidade da spec
está em `specs/002-hallucination-detection/checklists/requirements.md`.

A constituição foi emendada para a versão 1.1.0 em 2026-11-07. O princípio V
passa a permitir `GET /v1/traces/{trace_id}/check` e os campos de alucinação
no registro de revisão.

## Visão geral

Cada resposta de `POST /v1/chat` continua igual para o lojista. Depois que o
texto da resposta já está definido, o serviço mede se as afirmações dessa
resposta estão sustentadas por dados que ele já possui: passagens recuperadas
com nota, o retorno da ferramenta de suporte e a lista de citações emitida
pelo agente.

O resultado fica no `ReviewRecord` e pode ser lido sozinho em
`GET /v1/traces/{trace_id}/check`. O corpo dessa leitura traz só o veredito,
a confiança do veredito e os três checks. Não traz a resposta, as fontes, as
afirmações nem valores de ferramenta.

Há três vereditos: `verified`, `hallucinated` e `unverified`. A confiança do
veredito é o campo `verdict_confidence`. Ela não substitui o `confidence` que
o lojista já recebe no chat.

## Motivação

O serviço já recusava inventar taxa, prazo ou limite e já registrava rota,
ferramentas e notas de recuperação. Isso não diz se uma frase citada uma URL
que não foi recuperada, nem se um prazo de depósito diverge do retorno de
`get_receivables`.

A feature torna essa divergência mecânica e repetível, sem modelo pago e sem
comparar prosa livre. O teste não julga o texto da resposta. Julga citações,
notas e igualdade de campo.

## Arquitetura

O fluxo continua em um processo. Não há fila nova nem armazenamento durável.

```text
POST /v1/chat
  -> GuardrailAgent
  -> RouterAgent
  -> KnowledgeAgent | SupportAgent | EscalationAgent
  -> Reply                          (corpo do chat, sem veredito)
  -> evaluate()                     (app/observability/hallucination_check.py)
  -> ReviewRecord no TraceStore     (memória + uma linha JSON)
GET /v1/traces/{trace_id}           (registro completo)
GET /v1/traces/{trace_id}/check     (só o veredito)
```

`ChatService._finish` monta o `Reply` primeiro, com os mesmos campos de
antes. Em seguida chama `evaluate`. O veredito não volta para o texto, não
reabre o guardrail e não troca um handoff por uma recusa.

Quem emite as afirmações:

- **Produto, sem modelo.** `KnowledgeAgent.answer_product` gera uma
  `ClaimedStatement` por passagem que o retriever manteve. O texto é o da
  passagem. A citação é a URL. O nome do retriever vem de
  `BM25Retriever.name` (`bm25`) ou `ChromaRetriever.name` (`chroma`).
- **Produto, com modelo.** O prompt pede JSON `{"answer", "claims": [{"text",
  "citations"}]}`. Se o JSON é válido, essas claims são as afirmações. Se o
  modelo devolve prosa, a lista fica vazia. O serviço não varre a prosa para
  inventar citação. Lista vazia numa resposta factual faz
  `structured_output` falhar.
- **Produto sem passagem forte.** A resposta vira handoff por
  `insufficient_sources`, sem claims. O veredito fica `unverified`.
- **Suporte.** `SupportAgent._result` emite uma claim por campo que a
  resposta afirmou. A citação é o nome da ferramenta. `text` fica vazio.
  O valor fica só em `StatedField`, na memória, junto com o dicionário
  retornado pela ferramenta. Nenhum dos dois entra no registro.
- **Consulta geral, recusa e handoff sem fato.** Não há claim de produto nem
  de suporte. Os três checks ficam `not_applicable`.

Campos que o suporte afirma hoje:

| Caminho | Ferramenta | Campos |
| --- | --- | --- |
| Recebíveis encontrados | `get_receivables` | `status`, `amount_brl`, `expected_deposit` |
| Recebíveis ausentes | `get_receivables` | `status` |
| Perfil encontrado | `get_merchant_account` | `machine_model`, `pix_enabled`, `receiving_setup` |
| Perfil ausente | `get_merchant_account` | `status` |
| Terminal encontrado | `diagnose_terminal` | `machine_model`, `symptom`, `steps` |
| Terminal ausente | `diagnose_terminal` | `status` |

`sales_label` existe no retorno de recebíveis e está no escopo da spec, mas
a frase atual não o afirma, então não vira claim.

## Esquema da saída estruturada

Os modelos estão em `app/domain/models.py`. `extra` é proibido em todos.

### `ClaimedStatement`

| Campo | Tipo | Uso |
| --- | --- | --- |
| `kind` | `product` ou `support` | Qual check se aplica |
| `text` | string | Afirmação pública no produto. Vazio no suporte |
| `citations` | lista de strings | URL no produto. Nome da ferramenta no suporte |
| `fields` | lista de strings | Nomes de campo no suporte. Vazio no produto |

### Evidência

União discriminada por `kind`.

`SourceEvidence` (`retrieved_source`): `title`, `url`, `retriever` (`bm25` ou
`chroma`) e `score`. Só é gravada se a URL citada estava na lista recuperada.

`ToolEvidence` (`tool_comparison`): `tool`, `fields` e `matched`. `matched` é
igualdade exata entre o valor afirmado em memória e o valor no retorno da
ferramenta. O valor em si não é campo do modelo.

### `CheckResult`

Sempre três itens, nesta ordem:

| `name` | Quando vale | `pass` | `fail` | `not_applicable` |
| --- | --- | --- | --- | --- |
| `anchor` | Há claim de produto | Toda URL citada foi recuperada e a nota passa a barra | URL ausente na recuperação, nota menor que 0,15, ou nota menor que 94% da melhor nota da pergunta | Não há claim de produto |
| `tool_payload` | Há claim de suporte ou uma ferramenta de suporte rodou | Todo campo afirmado existe no retorno e é igual | Campo ausente no retorno, valor diferente, ou valor afirmado não foi entregue ao check | Não houve ferramenta de suporte nem claim de suporte |
| `structured_output` | Resposta factual de produto ou suporte, ou qualquer claim presente | A lista não está vazia e cada citação está nas `sources` (produto) ou nas ferramentas invocadas (suporte) | Lista vazia numa resposta factual, URL fora das sources, ou ferramenta citada que não foi chamada | Recusa, consulta geral, ou handoff sem claim |

A barra da âncora é a que o produto já usa para manter uma passagem.
`MIN_SCORE` em `app/rag/retriever.py` é `0.15`. `KEEP_RATIO` no check é
`0.94`. A nota citada precisa ser pelo menos `0.15` e pelo menos `0.94` vezes
a maior nota recuperada naquela pergunta. A comparação usa uma folga de
`1e-12` para não falhar por ruído binário.

Consulta de tempo e câmbio não entra na âncora: o serviço não guarda nota de
passagem Getnet para elas. `web_search` não dispara o check de ferramenta.

### `ReviewRecord`

Ganha cinco campos, além dos que já existiam (`trace_id`, `user_id`, `route`,
`intent`, `tools`, `sources`, `retrieval_scores`, `outcome`, `confidence`,
`handoff`, `latency_ms`):

- `claimed_statements`
- `evidence`
- `check_results`
- `verdict`
- `verdict_confidence`

### `CheckResponse`

| Campo | Conteúdo |
| --- | --- |
| `trace_id` | O mesmo UUID do chat |
| `verdict` | `verified`, `hallucinated` ou `unverified` |
| `verdict_confidence` | Número de 0 a 1 |
| `check_results` | Os três `CheckResult` |

## Vereditos e confiança

`verdict_confidence` mede a certeza do veredito, não a confiança da resposta
ao lojista.

| Veredito | Regra | Confiança |
| --- | --- | --- |
| `unverified` | Nenhum check se aplica | `0` |
| `verified` | Pelo menos um check se aplica e todos os aplicáveis passam | A menor nota citada, se houve passagem. `1` se a prova foi só de ferramenta |
| `hallucinated` | Qualquer check aplicável falha | `1` se a falha é mecânica: citação ausente, lista vazia ou campo de ferramenta divergente. Se a única falha é nota abaixo da barra, a confiança é a distância da barra até a pior nota citada, limitada ao intervalo de `0.01` a `1` |

Uma falha mecânica junto com uma nota baixa prevalece: a confiança fica `1`.
Um check `not_applicable` não derruba um veredito que já passou e não conta
como falha.

Exemplos medidos na demo da seção 5 de `DEMO.md`:

- Antecipação, com passagem mantida: `verified`, confiança igual à nota da
  passagem (cerca de `0.91` na execução local), `anchor` e
  `structured_output` em `pass`, `tool_payload` em `not_applicable`.
- Recusa do guardrail: `unverified`, confiança `0`, os três
  `not_applicable`. O mesmo vale para tempo, câmbio e pedido de pessoa.
- Claim de produto cuja URL não está nas sources nem na recuperação:
  `hallucinated`, confiança `1`, `anchor` e `structured_output` em `fail`.
  Esse caso não sai de uma mensagem de lojista. O chat não aceita citação
  enviada pelo chamador. O exemplo está no trecho Python da seção 5.

## Comportamento do guardrail

O `GuardrailAgent` não foi alterado. Ele continua sendo o primeiro passo e
ainda recusa mensagem vazia, tentativa de sobrepor as instruções e pedido de
dado de outro cliente. Essas respostas saem com `outcome` `refused`, sem
claim, e o check as marca `unverified`.

Uma falha de alucinação não é uma nova recusa. O check não chama o guardrail
de novo, não troca o texto e não impede um handoff que o fluxo já decidiu.
O `Reply` é construído antes de `evaluate`. O contrato do chat permanece
`trace_id`, `answer`, `route`, `sources`, `confidence`, `handoff` e
`tools_used`.

## Endpoint de check

```bash
RESP=$(curl -s localhost:8000/v1/chat \
  -H 'content-type: application/json' \
  -d '{"message":"How does receivables advance (antecipação) work with Getnet?","user_id":"cliente1988"}')
TRACE=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["trace_id"])' <<<"$RESP")
curl -s "localhost:8000/v1/traces/$TRACE/check"
```

`trace_id` que não é UUID, ou que não está na memória deste processo, responde
`404` com `{"detail":"Unknown trace"}` e sem corpo de veredito.

Swagger, ReDoc e o OpenAPI em tempo de execução continuam desligados
(`docs_url`, `redoc_url` e `openapi_url` são `None`). O contrato versionado
está em `specs/001-agent-orchestration/contracts/chat.openapi.yaml`, agora com
a rota de check e os esquemas novos.

## Rastreamento

`TraceStore` em `app/observability/traces.py` segue um dicionário no processo.
`put` grava o `ReviewRecord` inteiro e escreve uma linha JSON no logger
`getnet.assist`. A linha inclui claims, evidência, checks e veredito. Não
inclui `amount_brl` como valor, nome legal nem número de conta. O nome do
campo `amount_brl` pode aparecer na lista `fields`, porque a evidência registra
quais campos foram comparados.

O registro some quando o processo reinicia. Persistência durável ficou fora
desta feature.

`GET /v1/traces/{trace_id}` devolve o registro completo, inclusive os campos
novos. `GET /v1/traces/{trace_id}/check` só projeta os quatro campos do
`CheckResponse`.

## Testes

`tests/test_hallucination.py` cobre os dois lados de cada check e o HTTP, com
modelo falso e sem rede. A suíte completa do repositório passou com 33 testes
depois desta feature.

| Teste | O que fixa |
| --- | --- |
| `test_anchor_pass_records_source_and_score` | Âncora passa e a evidência traz título, URL, `bm25` e nota |
| `test_anchor_fail_when_score_is_under_the_keep_bar` | Nota 0,5 contra topo 0,8 falha só a âncora; confiança é a distância até a barra |
| `test_tool_payload_pass_and_terminal_fields_match` | `symptom` e `steps` iguais ao retorno |
| `test_tool_payload_fail_does_not_store_the_amount` | Depósito divergente falha; `1840`, o nome legal e os valores não entram no JSON |
| `test_structured_output_fails_when_the_citation_was_not_used` | URL fora das sources e ferramenta citada sem ter sido chamada |
| `test_empty_claim_list_on_a_factual_reply_fails_structured_output` | Prosa factual sem claims é `hallucinated` |
| `test_not_found_status_passes_and_a_stated_balance_fails` | `status=not_found` passa; afirmar depósito para usuário ausente falha |
| `test_account_field_mismatch_fails` | `machine_model` diferente falha |
| `test_check_route_is_slim_and_the_chat_reply_is_unchanged` | O check não vaza a resposta; o chat não ganha veredito |
| `test_receivables_trace_omits_the_amount` | O rastro de `cliente1988` não contém `1840` nem o nome legal |
| `test_refusal_handoff_and_general_questions_are_unverified` | Recusa, pessoa, tempo e euro |
| `test_unknown_and_malformed_check_ids_are_not_found` | UUID desconhecido e id malformado devolvem 404 |

`DEMO.md`, seção 5, repete o caminho HTTP de verificado e não verificado e o
trecho Python do caso alucinado. A seção 6 lembra que o `pytest` inclui esses
casos.

## Arquivos alterados

| Arquivo | Mudança |
| --- | --- |
| `specs/002-hallucination-detection/spec.md` | Contrato da feature. Status aceito. A emenda da constituição está registrada como feita |
| `specs/002-hallucination-detection/checklists/requirements.md` | Checklist de qualidade da spec, marcado |
| `.specify/memory/constitution.md` | Princípio V na versão 1.1.0: a rota de check e os campos do registro |
| `.specify/feature.json` | Aponta para `specs/002-hallucination-detection` |
| `app/domain/models.py` | `ClaimedStatement`, evidências, `CheckResult`, campos do `ReviewRecord`, `CheckResponse` |
| `app/observability/hallucination_check.py` | `evaluate` e as três regras, a barra e a confiança |
| `app/observability/traces.py` | O mesmo store em memória. O registro gravado agora inclui o veredito |
| `app/agents/knowledge.py` | Claims por passagem, ou o JSON do modelo. Prosa não vira citação |
| `app/agents/support.py` | Uma claim por campo afirmado. Valor só em `StatedField` |
| `app/orchestration/service.py` | `_finish` chama `evaluate` depois de montar o `Reply` |
| `app/rag/retriever.py` | `name` em `bm25` e `chroma`, para a evidência |
| `app/main.py` | `GET /v1/traces/{trace_id}/check`. 404 compartilhado com a leitura do rastro |
| `tests/test_hallucination.py` | Pass e fail de cada check, mais o contrato HTTP |
| `specs/001-agent-orchestration/contracts/chat.openapi.yaml` | Rota e esquemas do check |
| `DEMO.md` | Seção 5, com os três vereditos |

Fora desta entrega: banco para o rastro, reescrita da resposta quando o
veredito é `hallucinated`, segundo passe de guardrail, painel, e checagem de
tempo ou câmbio.
