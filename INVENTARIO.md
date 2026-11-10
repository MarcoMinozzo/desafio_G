# Inventário do Getnet Assist

Serviço HTTP de um processo. Um chat entra em `POST /v1/chat`, passa pelo guardrail e pelo roteador, e um especialista responde. Se a mesma mensagem pede a conta do lojista e um fato de produto, o suporte responde e o conhecimento responde em seguida. Não há fila, worker em segundo plano nem banco de aplicação. O estado de execução fica em três mapas na memória do processo: `TraceStore`, `SessionStore` e `MetricsStore`. Os três somem quando o processo reinicia.

Não existe `app.py`. A entrada é `app/main.py`, carregada pelo Uvicorn como `app.main:app`.

## Sequência de subida

`app = create_app()` no final de `app/main.py` roda na importação.

1. `Settings.from_env()` lê `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` (padrão `gpt-4o-mini`) e `GETNET_INGEST` (padrão ligado, a menos que seja `0`).
2. Se `ingest_on_start`: `ingest_specified_urls` baixa duas páginas da Getnet e regrava os Markdown. Falha de rede só registra aviso e segue com o disco.
3. `load_corpus` lê cada `data/corpus/*.md` como um `CorpusDocument` (um arquivo, um documento).
4. `build_retriever`: sempre monta o BM25. Com chave e `chromadb` importável, tenta `ChromaRetriever` e, se falhar, fica no BM25.
5. `build_llm`: sem chave devolve `NullLLM`; com chave, `OpenAICompatibleClient`.
6. `HttpWebSearch` (ou o fake injetado nos testes).
7. `load_merchants` lê `data/merchants.json`.
8. `corpus_age_days` mede a idade do Markdown mais antigo em `data/corpus`. `build_service` instancia `GuardrailAgent`, `RouterAgent(llm)`, `KnowledgeAgent(retriever, web, llm)`, `SupportAgent(merchants)`, `EscalationAgent`, `TraceStore`, `SessionStore` e `MetricsStore`, e os entrega a `ChatService`.

Não há job periódico. A ingestão é síncrona, só na subida (e via `python -m app.rag.ingest`).

## Pedido típico

`POST /v1/chat` com `message`, `user_id` e `session_id` opcional valida `ChatRequest` e chama `ChatService.handle`.

1. Cria `trace_id`. Se o corpo não traz `session_id`, gera um. Lê o último turno daquele par `user_id` + `session_id`, se existir, e monta o `Handoff` com a mensagem, o `user_id` e o turno anterior.
2. `GuardrailAgent.review`. Recusa (vazio, injeção, outro cliente) encerra com `outcome=refused`.
3. `RouterAgent.route`. Se a tabela vê conta e produto ao mesmo tempo, essa sequência vence. Senão, um intent válido do modelo vence a tabela. Se a tabela diz `out_of_scope` e o turno anterior deste lojista era produto, conta ou consulta geral, o turno continua o assunto anterior. Caso contrário, `_table`.
4. Confiança do roteador abaixo de 0,45, ou pedido de pessoa: `EscalationAgent.open`.
5. `out_of_scope`: recusa sem ferramenta.
6. `general_web`: `KnowledgeAgent.answer_general` (clima ou câmbio; não cita Getnet).
7. `account_support`: `SupportAgent.answer` chama uma ferramenta com o `user_id` do pedido.
8. `product_knowledge`: `KnowledgeAgent.answer_product`. Sem trecho forte, escala com `insufficient_sources`, a menos que o suporte já tenha respondido na mesma volta. Nesse caso a parte de produto declara a lacuna e a resposta da conta permanece.
9. Numa sequência, os passos 7 e 8 rodam os dois, nesta ordem. As respostas são juntadas por uma linha em branco.
10. `_finish` monta o `Reply` primeiro. `evaluate` mede as afirmações com os dados que a volta já tem. O `ReviewRecord` vai para o `TraceStore` (memória e uma linha JSON). O turno vai para o `SessionStore`. O `MetricsStore` conta o desfecho e o veredito.

`GET /v1/traces/{trace_id}` lê o registro completo. `GET /v1/traces/{trace_id}/check` lê só o veredito. `GET /v1/metrics` lê os contadores. `user_id` ou `session_id` inválido no corpo vira 422. Um `session_id` de outro `user_id` não abre o fio alheio: a chave é o par.

## Fluxo de uma pergunta de produto

Pergunta → `retriever.search(message, k=3)` → até três `Hit`.

- BM25: `tokenize` da pergunta, `BM25Okapi.get_scores` (relevância Okapi por documento). `value / (value + 1)` se `value > 0`.
- Chroma: a pergunta vira um embedding `text-embedding-3-small`; `collection.query` devolve distâncias. Nota = `1 / (1 + distance)`.

Cada documento do corpus já é um vetor (ou um documento BM25). Não há corte de PDF nem de parágrafo. O texto embutido é `título + "\n" + corpo`.

Depois do search: ficam trechos com nota ≥ `MIN_SCORE` (0,15). O corte relativo é 94% da melhor nota e só descarta trechos piores; o melhor sempre permanece. Todas as passagens recuperadas, inclusive as descartadas, seguem como `RetrievedPassage` para o check de âncora. Se `strong` fica vazio, confiança fixa 0,2, sem claims, e handoff. Se há trechos, `_prompt` junta título, URL e texto com `"\n\n".join` e uma única chamada `llm.answer(PRODUCT_SYSTEM, prompt)`. Sem texto do modelo, a resposta é o extrato dos trechos mantidos e há uma claim por passagem, citando a URL. Com JSON válido `{"answer", "claims"}`, as claims são as do modelo. Com prosa, a lista fica vazia: o serviço não varre o texto para inventar citação. Confiança = `min(0,95, nota do melhor trecho)`. Trechos removidos não entram nessa conta. O resultado é um `KnowledgeResult`, com o nome do retriever (`bm25` ou `chroma`).

`answer_general` não busca no corpus nem chama o modelo: `web.lookup`. Sem texto, confiança 0,35; com texto, 0,8.

## Docker

`Dockerfile`: imagem `python:3.12-slim`, copia `pyproject.toml`, `README.md`, `app/` e `data/`, `pip install .`, expõe 8000, comando `uvicorn app.main:app --host 0.0.0.0 --port 8000`. O extra `llm` (openai, chromadb) não entra na imagem padrão.

`docker-compose.yml`: serviço `assist`, porta 8000, repassa `OPENAI_*` e `GETNET_INGEST` (padrão 1).

## app/

### `app/__init__.py`

Pacote raiz. Sem símbolos.

### `app/main.py`

Superfície HTTP e montagem do processo.

- `create_app`: sobe ingestão, corpus, retriever, LLM, web, idade do corpus, serviço e as rotas.
- `invalid_request`: 422 em corpo inválido.
- `load_trace`: exige UUID e registro existente; senão 404.
- `create_chat`: `POST /v1/chat` → `service.handle`.
- `read_metrics`: `GET /v1/metrics`.
- `read_check`: `GET /v1/traces/{trace_id}/check`.
- `read_trace`: `GET /v1/traces/{trace_id}`.
- `app`: instância criada na importação.

Importa de: `config`, `domain.models`, `llm.client`, `observability.metrics`, `orchestration.service`, `rag.corpus`, `rag.ingest`, `rag.retriever`, `tools.store`, `tools.web_search`.

Quem chama: Uvicorn; `tests/conftest.py`; `tests/test_orchestration.py`.

### `app/config.py`

Configuração a partir do ambiente.

- `ROOT`: raiz do repositório.
- `Settings`: chave, URL e modelo OpenAI, pastas do corpus, merchants e Chroma, flag de ingestão.
- `Settings.from_env`.

Importa só da biblioteca padrão. Quem chama: `main`, `retriever`, testes (`conftest`, `test_ingest`, `test_retrieval`).

## app/domain/

### `app/domain/__init__.py`

Pacote. Sem símbolos.

### `app/domain/models.py`

Contrato Pydantic do chat, do registro de revisão, da leitura do check e do snapshot de métricas.

- Literais: `RouteName`, `ToolName`, `IntentName`, `OutcomeName`, `HandoffReason`, `ClaimKind`, `CheckName`, `CheckStatus`, `VerdictName`, `RetrieverName`.
- `PublicSource`: título e URL citados.
- `Handoff`: recibo `ESC-` + 8 caracteres e o motivo.
- `ChatRequest`: `message`, `user_id` e `session_id` opcional.
- `Reply`: resposta ao cliente, com `session_id`. Não leva veredito.
- `ClaimedStatement`, `SourceEvidence`, `ToolEvidence`, `CheckResult`: afirmação, evidência e um check.
- `ReviewRecord`: visão do operador, sem payload bruto. Inclui claims, evidência, checks, veredito e `session_id`.
- `CheckResponse`: só `trace_id`, veredito, confiança do veredito e os três checks.
- `MetricsSnapshot`: contagens, idade do corpus e nomes de alerta. Sem `user_id` e sem valor de ferramenta.

Quem chama: `main`, `service`, `escalation`, `knowledge`, `support`, `hallucination_check`, `metrics`, `traces`. Não importa outros módulos do projeto.

## app/llm/

### `app/llm/__init__.py`

Pacote. Sem símbolos.

### `app/llm/client.py`

Fronteira do modelo. Testes injetam um fake. O cliente OpenAI só corre com chave.

- `ROUTER_SYSTEM`: prompt de classificação em JSON.
- `LLMClient`: protocolo com `classify` e `answer`.
- `NullLLM`: devolve `None` (caminho offline).
- `FakeLLM`: intent e resposta roteirizados para teste.
- `OpenAICompatibleClient`: chat completions; sem chave ou sem o pacote `openai`, devolve `None`.
- `build_llm`: `NullLLM` ou cliente real.
- `_parse_intent`: lê o JSON do classificador.

Quem chama: `main` (`build_llm`), `service` (tipo), `router` (`classify`), `knowledge` (`answer`), `tests/test_orchestration.py` (`FakeLLM`).

## app/orchestration/

### `app/orchestration/__init__.py`

Pacote. Sem símbolos.

### `app/orchestration/handoff.py`

- `Handoff`: objeto em memória (`trace_id`, `intent`, `confidence`, `payload`) passado de agente a agente.

Quem chama: `service`, `guardrail`, `router`, `knowledge`, `support`. Não confundir com `domain.models.Handoff`, que é o recibo ao cliente.

### `app/orchestration/sessions.py`

Memória do fio, só no processo. A chave é `(user_id, session_id)`.

- `MemoryTurn`: mensagem do lojista, intent, detalhe e `topic`. O `topic` é a pergunta que a busca deve repetir num seguimento. Não há valor de ferramenta.
- `SessionStore.latest`: último turno daquele par, ou nada.
- `SessionStore.remember`: guarda no máximo quatro turnos.

Quem chama: `ChatService`. Um `session_id` apresentado por outro `user_id` não encontra o fio.

### `app/orchestration/service.py`

Dono do fluxo. O roteador pode mandar o suporte e depois o conhecimento na mesma volta.

- `_REFUSALS`: textos de recusa.
- `ChatService.handle`: sequência descrita acima. Num seguimento, a busca usa o `topic` anterior, não o fragmento novo.
- `ChatService._escalate`: abre handoff e finaliza.
- `ChatService._finish`: monta o `Reply`, chama `evaluate`, grava o traço, lembra o turno e conta a métrica.
- `build_service`: liga os cinco agentes, o traço, a sessão e as métricas.

Importa os cinco agentes, modelos, `LLMClient`, `evaluate`, `MetricsStore`, `TraceStore`, `MemoryTurn`, `SessionStore`, os dois `Handoff`, os retrievers e `WebSearch`. Quem chama: `main.create_app`.

## app/agents/

### `app/agents/__init__.py`

Pacote. Sem símbolos.

### `app/agents/guardrail.py`

Recusa mensagem vazia, tentativa de furar a instrução e leitura de outro cliente.

- `_INJECTION`, `_OTHER_CUSTOMER`, `_USER_ID`: padrões.
- `GuardrailDecision`: `allowed` e `reason`.
- `GuardrailAgent.review`.

Importa `orchestration.handoff.Handoff`. Quem chama: `service`; `tests/test_guardrail.py` chama o agente direto.

### `app/agents/router.py`

Escolhe o intent. Pedido de pessoa, clima e câmbio continuam exclusivos. Conta e produto são sinais independentes: se os dois aparecem, a sequência é suporte e depois conhecimento, e essa sequência vence o modelo.

- `ALLOWED`: os cinco intents.
- `RouteDecision`: intent, detalhe, confiança, `sequence` e `continued`. `steps` devolve a sequência, ou o intent sozinho.
- `RouterAgent.route`: sequência dupla da tabela, senão `llm.classify`, senão continuação do turno anterior, senão `_table`.
- `_table`, `_account`, `_product`, `_continue`, `_detail`, `_fold`, `_contains`.

Importa `LLMClient` e `Handoff`. Quem chama: `service`.

### `app/agents/knowledge.py`

Resposta de produto a partir do corpus, e consulta geral que não cita página da Getnet.

- `PRODUCT_SYSTEM`: pede JSON com `answer` e `claims`. Cada citação é uma URL dos trechos.
- `KnowledgeResult`: resposta, confiança, fontes, ferramentas, notas, `insufficient`, claims, passagens recuperadas e nome do retriever.
- `KnowledgeAgent.answer_product`: busca, corte, prompt único, claims do modelo, do extrato, ou lista vazia se a resposta for prosa.
- `KnowledgeAgent.answer_general`: `web.lookup`. Não emite claim.
- `_prompt`: junta a pergunta e os trechos numa string.
- `_claims_from_model`: lê o JSON. Prosa não vira citação.

Importa `ClaimedStatement`, `PublicSource`, `LLMClient`, `RetrievedPassage`, `Handoff`, tipos do retriever e `WebSearch`. Quem chama: `service` (`answer_product` e `answer_general`). `_prompt` só é avaliada como argumento de `llm.answer` na linha do produto; um `NullLLM` ainda recebe o texto e não chama modelo.

### `app/agents/support.py`

Conta do lojista. Toda ferramenta recebe o `user_id` do pedido.

- `SupportResult`: resposta, confiança, ferramentas, claims, `stated` e `payload`. O valor fica em `stated` e em `payload`, só na memória da volta.
- `SupportAgent.answer`: despacha por `detail` para `_receivables`, `_profile` ou `_terminal`.
- `SupportAgent._result`: uma `ClaimedStatement` de suporte por campo afirmado. A citação é o nome da ferramenta. O texto da claim fica vazio.

Importa `ClaimedStatement`, `StatedField`, `Handoff` e as três ferramentas. Quem chama: `service`.

### `app/agents/escalation.py`

- `EscalationAgent.open`: recibo `ESC-` + 8 hex e o motivo.

Importa o `Handoff` de domínio. Quem chama: `service._escalate`.

## app/rag/

### `app/rag/__init__.py`

Pacote. Sem símbolos.

### `app/rag/corpus.py`

Carrega o corpus curado.

- `CorpusDocument`: `id` (nome do arquivo), `title`, `url`, `body`.
- `load_corpus`: um `*.md` por documento.
- `_split_front_matter`: separa o cabeçalho YAML do corpo. Não fatia o texto.

Quem chama: `main`, `test_ingest`, `test_retrieval`. `retriever` usa o tipo.

### `app/rag/ingest.py`

Baixa duas URLs do briefing e grava Markdown. Pode rodar como `python -m app.rag.ingest`.

- `SPECIFIED_URLS`.
- `_PageText`: extrai texto visível do HTML.
- `document_id`, `extract_page`, `fetch_html`, `write_document`.
- `ingest_specified_urls`: baixa, extrai e substitui os arquivos.
- `main`.

Não importa outros módulos do projeto. Quem chama: `main.create_app` e `tests/test_ingest.py`.

### `app/rag/retriever.py`

Busca lexical, com Chroma opcional quando há chave.

- `MIN_SCORE` = 0,15.
- `_STOPWORDS`.
- `Hit`: um trecho com nota.
- `BM25Retriever`: `name = "bm25"`. `search` usa Okapi e `value / (value + 1)`.
- `ChromaRetriever`: `name = "chroma"`. Cliente persistente em `data/.chroma`, coleção única `getnet-corpus`, embeddings `text-embedding-3-small` de título e corpo, `upsert` na construção, `query` na busca, nota `1 / (1 + distance)`.
- `build_retriever`: BM25, ou Chroma se a chave existir e a criação não falhar.
- `tokenize`: letras e números, sem acento e sem stopword. Símbolo de fórmula some.

Importa `Settings` e `CorpusDocument`. Quem chama: `main` (`build_retriever`); `knowledge` e `service` usam os tipos e `search`. Teste de retrieval instancia `BM25Retriever` direto.

Não há código que trate LaTeX ou equação. O corpus não contém notação matemática. O embedding recebe a string crua.

## app/tools/

### `app/tools/__init__.py`

Pacote. Sem símbolos.

### `app/tools/store.py`

Fixture de lojistas.

- `load_merchants`: JSON objeto chaveado por `user_id`.
- `merchant_for`: o registro ou `None`.

Quem chama: `main` (`load_merchants`); `merchant`, `receivables` e `terminal` (`merchant_for`); testes de orquestração.

### `app/tools/merchant.py`

- `get_merchant_account`: modelo da máquina, Pix e setup de recebimento, ou `not_found`.

Quem chama: `SupportAgent._profile`; teste de orquestração.

### `app/tools/receivables.py`

- `get_receivables`: valor, status e data de depósito, ou `not_found`.

Quem chama: `SupportAgent._receivables`; teste de orquestração.

### `app/tools/terminal.py`

- `diagnose_terminal`: passos da maquininha para `decline` ou `connectivity`.

Quem chama: `SupportAgent._terminal`; teste de orquestração.

### `app/tools/web_search.py`

Clima e cotação do euro. Nunca é fonte Getnet.

- `PORTO_ALEGRE`.
- `WebSearch.lookup`.
- `FakeWebSearch`: respostas fixas para teste.
- `HttpWebSearch`: Open-Meteo e Frankfurter.
- `_weather`, `_euro_rate`.

Quem chama: `main`, `KnowledgeAgent.answer_general`, `conftest` e `test_orchestration` (fake).

## app/observability/

### `app/observability/__init__.py`

Pacote. Sem símbolos.

### `app/observability/traces.py`

- `TraceStore.put`: guarda o `ReviewRecord` inteiro, inclusive claims, evidência, checks e veredito, e escreve uma linha JSON no logger `getnet.assist`.
- `TraceStore.get`.

Importa `ReviewRecord`. Quem chama: `build_service` e `ChatService._finish`; as rotas de trace e de check leem `service.traces`.

### `app/observability/hallucination_check.py`

Três checks mecânicos sobre dados que a resposta já tem. Não grava valor de ferramenta.

- `KEEP_RATIO` = 0,94. A barra absoluta continua `MIN_SCORE` (0,15).
- `RetrievedPassage`, `StatedField`, `HallucinationReport`.
- `evaluate`: evidência, `anchor`, `tool_payload`, `structured_output`, veredito e `verdict_confidence`.
- `_anchor`, `_tool_payload`, `_structured`, `_source_evidence`, `_tool_evidence`, `_verdict`.

Quem chama: `ChatService._finish`. `knowledge` usa `RetrievedPassage`. `support` usa `StatedField`.

### `app/observability/metrics.py`

Contadores e alertas. O snapshot não tem `user_id` nem valor de ferramenta.

- `MIN_SAMPLE` = 10, `HALLUCINATED_RATIO` = 0,3, `HANDOFF_RATIO` = 0,5, `CORPUS_MAX_AGE_DAYS` = 30.
- `MetricsStore.record`: soma pedido, desfecho e veredito, e emite alerta novo.
- `MetricsStore.alerts` e `snapshot`.
- `corpus_age_days`: idade, em dias, do `*.md` mais antigo do corpus. Diretório vazio vale 0.
- Logger `getnet.assist.metrics`. Um aviso JSON quando `corpus_stale`, `hallucinated_ratio` ou `handoff_ratio` passa a valer. O mesmo alerta não se repete no processo.

Quem chama: `main.create_app` (idade e store) e `ChatService._finish` (`record`). A rota de métricas lê `service.metrics`.

## tests/

Sem rede e sem modelo pago, via `create_app` com `FakeWebSearch` e settings offline.

- `conftest.py`: `offline_settings`, `client` (`TestClient`), `scenarios` (lê `data/evaluation.yaml`).
- `test_contract.py`: forma do chat, inclusive `session_id`, trace desconhecido, `user_id` inválido, trace sem payload do cliente.
- `test_guardrail.py`: vazio, injeção, outro cliente, tema fora de escopo, e o agente direto.
- `test_orchestration.py`: depósito, usuário desconhecido, maquininha, ferramentas que ignoram id no texto, perfil, handoff humano, intent do `FakeLLM` vencendo a tabela.
- `test_evaluation.py`: os cenários do YAML batem com especialista e ferramenta; perguntas gerais não citam Getnet.
- `test_retrieval.py`: antecipação e link de pagamento acertam o Markdown certo, só BM25.
- `test_ingest.py`: extração de HTML e presença das duas URLs no corpus.
- `test_hallucination.py`: passa e falha de âncora, payload e saída estruturada, rota de check enxuta, valor de venda ausente do registro, recusa e consulta geral `unverified`, id desconhecido.
- `test_improvements.py`: pergunta mista roda suporte e depois conhecimento, seguimento no mesmo `user_id`, outro `user_id` não herda o assunto, snapshot sem dado de cliente, alertas de razão e corpus velho.

## Outros arquivos de fonte

- `pyproject.toml`: pacote `getnet-assist`, dependências de runtime e extra opcional `llm` (`openai`, `chromadb`).
- `data/corpus/*.md`: sete resumos públicos e os dois Markdown baixados de `getnet.net` e `getnet.net/en`. Um arquivo, um documento de busca.
- `data/merchants.json`: fixture, não conta ao vivo.
- `data/evaluation.yaml`: dez cenários oficiais. Cada um continua com um especialista.
- `specs/001-agent-orchestration/`: spec da orquestração, plano, modelo de dados, tarefas, quickstart e o contrato OpenAPI, que também descreve o check, a sessão e as métricas. Não é importado pelo serviço.
- `specs/002-hallucination-detection/`: spec do veredito e o checklist de qualidade. Não é importado pelo serviço.
- `.specify/`: memória e templates do Spec Kit. A constituição está na versão 1.2.0.

## Quem chama quem

```text
uvicorn app.main:app
  create_app
    ingest_specified_urls          (se GETNET_INGEST != 0)
    load_corpus
    build_retriever
      BM25Retriever | ChromaRetriever
    build_llm
    HttpWebSearch
    load_merchants
    corpus_age_days
    build_service
      GuardrailAgent, RouterAgent, KnowledgeAgent,
      SupportAgent, EscalationAgent, TraceStore,
      SessionStore, MetricsStore
  POST /v1/chat
    ChatService.handle
      SessionStore.latest
      GuardrailAgent.review
      RouterAgent.route
        _table (sequência) | llm.classify | _continue
      KnowledgeAgent.answer_product
        retriever.search
        _prompt + llm.answer       (ou extrato, ou claims do JSON)
      KnowledgeAgent.answer_general
        web.lookup
      SupportAgent.answer
        get_receivables | get_merchant_account | diagnose_terminal
      EscalationAgent.open
      evaluate
      TraceStore.put
      SessionStore.remember
      MetricsStore.record
  GET /v1/traces/{trace_id}
  GET /v1/traces/{trace_id}/check
  GET /v1/metrics
```
