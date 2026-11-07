# Inventário do Getnet Assist

Serviço HTTP de um processo. Um chat entra em `POST /v1/chat`, passa pelo guardrail e pelo roteador, e um especialista responde. Não há fila, worker em segundo plano nem banco de aplicação. O único estado de execução é o `TraceStore` em memória.

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
8. `build_service` instancia `GuardrailAgent`, `RouterAgent(llm)`, `KnowledgeAgent(retriever, web, llm)`, `SupportAgent(merchants)`, `EscalationAgent` e `TraceStore`, e os entrega a `ChatService`.

Não há job periódico. A ingestão é síncrona, só na subida (e via `python -m app.rag.ingest`).

## Pedido típico

`POST /v1/chat` com `message` e `user_id` valida `ChatRequest` e chama `ChatService.handle`.

1. Cria `trace_id` e um `Handoff` com a mensagem e o `user_id`.
2. `GuardrailAgent.review`. Recusa (vazio, injeção, outro cliente) encerra com `outcome=refused`.
3. `RouterAgent.route`. O modelo, se devolver um intent válido, vence a tabela de palavras. Senão, `_table`.
4. Confiança do roteador abaixo de 0,45, ou pedido de pessoa: `EscalationAgent.open`.
5. `out_of_scope`: recusa sem ferramenta.
6. `general_web`: `KnowledgeAgent.answer_general` (clima ou câmbio; não cita Getnet).
7. `account_support`: `SupportAgent.answer` chama uma ferramenta com o `user_id` do pedido.
8. Caso restante, `product_knowledge`: `KnowledgeAgent.answer_product`. Sem trecho forte, escala com `insufficient_sources`.
9. `_finish` grava `ReviewRecord` no `TraceStore` (memória e uma linha JSON de log) e devolve `Reply`.

`GET /v1/traces/{trace_id}` lê esse registro. `user_id` inválido no corpo vira 422.

## Fluxo de uma pergunta de produto

Pergunta → `retriever.search(message, k=3)` → até três `Hit`.

- BM25: `tokenize` da pergunta, `BM25Okapi.get_scores` (relevância Okapi por documento). `value / (value + 1)` se `value > 0`.
- Chroma: a pergunta vira um embedding `text-embedding-3-small`; `collection.query` devolve distâncias. Nota = `1 / (1 + distance)`.

Cada documento do corpus já é um vetor (ou um documento BM25). Não há corte de PDF nem de parágrafo. O texto embutido é `título + "\n" + corpo`.

Depois do search: ficam trechos com nota ≥ `MIN_SCORE` (0,15). O corte relativo é 94% da melhor nota e só descarta trechos piores; o melhor sempre permanece. Se `strong` fica vazio, confiança fixa 0,2 e handoff. Se há trechos, `_prompt` junta título, URL e texto com `"\n\n".join` e uma única chamada `llm.answer(PRODUCT_SYSTEM, prompt)`. Sem texto do modelo, a resposta é o extrato dos mesmos trechos. Confiança = `min(0,95, nota do melhor trecho)`. Trechos removidos não entram nessa conta. O resultado é um `KnowledgeResult`.

`answer_general` não busca no corpus nem chama o modelo: `web.lookup`. Sem texto, confiança 0,35; com texto, 0,8.

## Docker

`Dockerfile`: imagem `python:3.12-slim`, copia `pyproject.toml`, `README.md`, `app/` e `data/`, `pip install .`, expõe 8000, comando `uvicorn app.main:app --host 0.0.0.0 --port 8000`. O extra `llm` (openai, chromadb) não entra na imagem padrão.

`docker-compose.yml`: serviço `assist`, porta 8000, repassa `OPENAI_*` e `GETNET_INGEST` (padrão 1).

## app/

### `app/__init__.py`

Pacote raiz. Sem símbolos.

### `app/main.py`

Superfície HTTP e montagem do processo.

- `create_app`: sobe ingestão, corpus, retriever, LLM, web, serviço e as rotas.
- `invalid_request`: 422 em corpo inválido.
- `create_chat`: `POST /v1/chat` → `service.handle`.
- `read_trace`: `GET /v1/traces/{trace_id}`.
- `app`: instância criada na importação.

Importa de: `config`, `domain.models`, `llm.client`, `orchestration.service`, `rag.corpus`, `rag.ingest`, `rag.retriever`, `tools.store`, `tools.web_search`.

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

Contrato Pydantic das duas rotas.

- Literais: `RouteName`, `ToolName`, `IntentName`, `OutcomeName`, `HandoffReason`.
- `PublicSource`: título e URL citados.
- `Handoff`: recibo `ESC-` + 8 caracteres e o motivo.
- `ChatRequest`: `message` e `user_id`.
- `Reply`: resposta ao cliente.
- `ReviewRecord`: visão do operador, sem payload bruto.

Quem chama: `main`, `service`, `escalation`, `knowledge` (`PublicSource`), `traces`. Não importa outros módulos do projeto.

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

### `app/orchestration/service.py`

Dono do fluxo. Um especialista depois do guardrail e do roteador.

- `_REFUSALS`: textos de recusa.
- `ChatService.handle`: sequência descrita acima.
- `ChatService._escalate`: abre handoff e finaliza.
- `ChatService._finish`: monta `Reply`, grava o traço, mede latência.
- `build_service`: liga os cinco agentes e o store.

Importa os cinco agentes, modelos, `LLMClient`, `TraceStore`, os dois `Handoff`, os retrievers e `WebSearch`. Quem chama: `main.create_app`.

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

Escolhe o intent. Um intent válido do modelo substitui a tabela.

- `ALLOWED`: os cinco intents.
- `RouteDecision`: intent, detalhe, confiança.
- `RouterAgent.route`: tenta `llm.classify` e cai em `_table`.
- `_table`, `_detail`, `_fold`, `_contains`: regras por palavra.

Importa `LLMClient` e `Handoff`. Quem chama: `service`.

### `app/agents/knowledge.py`

Resposta de produto a partir do corpus, e consulta geral que não cita página da Getnet.

- `PRODUCT_SYSTEM`: instrução do modelo para não inventar fora dos trechos.
- `KnowledgeResult`: resposta, confiança, fontes, ferramentas, notas, `insufficient`.
- `KnowledgeAgent.answer_product`: busca, corte, prompt único, LLM ou extrato.
- `KnowledgeAgent.answer_general`: `web.lookup`.
- `_prompt`: junta a pergunta e os trechos numa string.

Importa `PublicSource`, `LLMClient`, `Handoff`, tipos do retriever e `WebSearch`. Quem chama: `service` (`answer_product` e `answer_general`). `_prompt` só é avaliada como argumento de `llm.answer` na linha do produto; um `NullLLM` ainda recebe o texto e não chama modelo.

### `app/agents/support.py`

Conta do lojista. Toda ferramenta recebe o `user_id` do pedido.

- `SupportResult`.
- `SupportAgent.answer`: despacha por `detail` para `_receivables`, `_profile` ou `_terminal`.

Importa `Handoff` e as três ferramentas. Quem chama: `service`.

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
- `BM25Retriever.search`: Okapi e `value / (value + 1)`.
- `ChromaRetriever`: cliente persistente em `data/.chroma`, coleção única `getnet-corpus`, embeddings `text-embedding-3-small` de título e corpo, `upsert` na construção, `query` na busca, nota `1 / (1 + distance)`.
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

- `TraceStore.put`: guarda o `ReviewRecord` e escreve uma linha JSON.
- `TraceStore.get`.

Importa `ReviewRecord`. Quem chama: `build_service` e `ChatService._finish`; a rota de trace lê `service.traces`.

## tests/

Sem rede e sem modelo pago, via `create_app` com `FakeWebSearch` e settings offline.

- `conftest.py`: `offline_settings`, `client` (`TestClient`), `scenarios` (lê `data/evaluation.yaml`).
- `test_contract.py`: forma do chat, trace desconhecido, `user_id` inválido, trace sem payload do cliente.
- `test_guardrail.py`: vazio, injeção, outro cliente, tema fora de escopo, e o agente direto.
- `test_orchestration.py`: depósito, usuário desconhecido, maquininha, ferramentas que ignoram id no texto, perfil, handoff humano, intent do `FakeLLM` vencendo a tabela.
- `test_evaluation.py`: os cenários do YAML batem com especialista e ferramenta; perguntas gerais não citam Getnet.
- `test_retrieval.py`: antecipação e link de pagamento acertam o Markdown certo, só BM25.
- `test_ingest.py`: extração de HTML e presença das duas URLs no corpus.

## Outros arquivos de fonte

- `pyproject.toml`: pacote `getnet-assist`, dependências de runtime e extra opcional `llm` (`openai`, `chromadb`).
- `data/corpus/*.md`: nove resumos públicos. Um arquivo, um documento de busca.
- `data/merchants.json`: fixture, não conta ao vivo.
- `data/evaluation.yaml`: dez cenários oficiais.
- `specs/001-agent-orchestration/`: spec, plano, modelo de dados, tarefas, quickstart, contrato OpenAPI. Não é importado pelo serviço.
- `.specify/`: memória e templates do Spec Kit, inclusive a constituição.

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
    build_service
      GuardrailAgent, RouterAgent, KnowledgeAgent,
      SupportAgent, EscalationAgent, TraceStore
  POST /v1/chat
    ChatService.handle
      GuardrailAgent.review
      RouterAgent.route
        llm.classify | _table
      KnowledgeAgent.answer_product
        retriever.search
        _prompt + llm.answer       (ou extrato)
      KnowledgeAgent.answer_general
        web.lookup
      SupportAgent.answer
        get_receivables | get_merchant_account | diagnose_terminal
      EscalationAgent.open
      TraceStore.put
```
