# Especificação da feature: detecção de alucinação

Tradução de `specs/002-hallucination-detection/spec.md`. O arquivo em inglês continua sendo a spec do Spec Kit.

**Ramo da feature**: `002-hallucination-detection`

**Criada em**: 2026-11-07

**Status**: Aceita

**Entrada**: Descrição do usuário: "Medir se uma resposta do Getnet Assist alucinou, usando só dados que o serviço já tem para essa resposta: passagens recuperadas e suas notas, o retorno da ferramenta de suporte e as afirmações que o agente emitiu. Estender o registro de revisão com as afirmações, a evidência, os resultados dos checks e um veredito. Expor esses resultados numa leitura separada. Não inventar evidência nova, não guardar uma segunda cópia dos dados do cliente e não mudar a resposta do lojista."

## Cenários de uso e testes *(obrigatório)*

### História 1 — Ver se uma afirmação de produto está ancorada (Prioridade: P1)

Um revisor abre uma resposta de produto e vê cada afirmação do especialista de conhecimento, a passagem pública que deveria sustentá-la e se essa passagem foi de fato recuperada com força suficiente para ser mantida.

**Por que esta prioridade**: Taxas, prazos e limites inventados são a falha que a constituição já proíbe. Este é o check que torna essa falha visível.

**Teste independente**: Enviar uma pergunta de produto cuja resposta cita uma passagem mantida, e uma resposta de produto que cita uma passagem abaixo da barra de manutenção. Confirmar que a primeira passa e a segunda falha, sem chamar um serviço de linguagem pago.

**Cenários de aceitação**:

1. **Dado** uma resposta de produto que afirma um fato e cita uma passagem que o retriever manteve para essa pergunta, **quando** o revisor lê o check, **então** o check de âncora passa e a evidência nomeia o título da passagem, o endereço público, o retriever (`bm25` ou `chroma`) e a nota.
2. **Dado** uma resposta de produto que afirma um fato e cita uma passagem recuperada cuja nota está abaixo da barra de manutenção, **quando** o revisor lê o check, **então** o check de âncora falha.
3. **Dado** uma resposta de produto que admite que o material público é insuficiente e não afirma fato de produto, **quando** o revisor lê o check, **então** o check de âncora não se aplica e a resposta não é marcada como alucinada por falta de citação.

---

### História 2 — Ver se uma afirmação de conta bate com a ferramenta (Prioridade: P1)

Um revisor abre uma resposta de conta ou de terminal e vê se cada campo que o especialista de suporte afirmou coincide com o retorno da ferramenta para o mesmo `user_id`. A comparação usa o retorno que o serviço já calculou. O registro gravado não guarda o retorno bruto.

**Por que esta prioridade**: Uma resposta de suporte que discorda do próprio registro do lojista é uma alucinação mesmo quando a rota e o nome da ferramenta estão corretos.

**Teste independente**: Enviar uma pergunta de recebíveis cujo prazo de depósito afirmado é igual ao retorno da ferramenta, e outra cujo prazo não é. Confirmar passa e falha. Confirmar que o registro gravado contém o nome do campo e o resultado, e não contém o valor.

**Cenários de aceitação**:

1. **Dado** o lojista `cliente1988` e uma resposta de recebíveis cujo `expected_deposit` é igual a `get_receivables` para esse usuário, **quando** o revisor lê o check, **então** o check de payload da ferramenta passa.
2. **Dado** o mesmo lojista e uma resposta de recebíveis cujo `expected_deposit` difere de `get_receivables`, **quando** o revisor lê o check, **então** o check de payload da ferramenta falha.
3. **Dado** uma resposta de terminal que afirma `symptom` e `steps` iguais a `diagnose_terminal` para esse usuário e esse sintoma, **quando** o revisor lê o check, **então** o check de payload da ferramenta passa.
4. **Dado** uma resposta de conta que afirma `machine_model`, `pix_enabled` ou `receiving_setup` de forma diferente de `get_merchant_account` para esse usuário, **quando** o revisor lê o check, **então** o check de payload da ferramenta falha.
5. **Dado** qualquer check de payload da ferramenta, passando ou falhando, **quando** o registro de revisão é gravado, **então** ele não contém `amount_brl`, um nome legal nem um número de conta. O valor pode ser comparado em memória e depois descartado.

---

### História 3 — Rejeitar uma citação que nunca foi recuperada (Prioridade: P1)

O agente que responde emite afirmações como citações estruturadas, não como prosa sem checagem. Uma citação que não está nas fontes ou nas ferramentas desta resposta falha, mesmo que a frase soe plausível.

**Por que esta prioridade**: O check de âncora e o check de ferramenta não significam nada se o agente pode citar algo que o serviço não usou.

**Teste independente**: Alimentar uma lista de afirmações cujas URLs de citação estão todas nas fontes da resposta, e outra lista que cita uma URL que a resposta não usou. Confirmar passa e falha com um modelo falso. Similaridade de prosa não é avaliada.

**Cenários de aceitação**:

1. **Dado** uma resposta de produto em que toda afirmação cita uma URL presente nas fontes dessa resposta, **quando** o check roda, **então** o check de saída estruturada passa.
2. **Dado** uma resposta de produto que afirma um fato citando uma URL ausente das fontes dessa resposta, **quando** o check roda, **então** o check de saída estruturada falha.
3. **Dado** uma resposta de suporte em que toda afirmação cita um nome de ferramenta que foi de fato invocado nessa resposta, **quando** o check roda, **então** o check de saída estruturada passa.
4. **Dado** uma resposta de suporte que cita `get_receivables` quando essa ferramenta não foi invocada, **quando** o check roda, **então** o check de saída estruturada falha.
5. **Dado** uma resposta de produto ou de suporte que contém prosa factual mas uma lista de afirmações vazia, **quando** o check roda, **então** o check de saída estruturada falha. O serviço não inventa afirmações lendo a prosa.

---

### História 4 — Ler o veredito sem o resto da resposta (Prioridade: P2)

Um revisor que já tem um `trace_id` pode pedir só o resultado de alucinação: o veredito, o quanto esse veredito é certo e passa ou falha de cada check.

**Por que esta prioridade**: O registro de revisão completo é a auditoria da resposta. A leitura do check existe para que um avaliador pontue a alucinação sem analisar a resposta, as fontes ou o caminho das ferramentas.

**Teste independente**: Concluir uma resposta checada, ler a rota de check e confirmar que o corpo tem só os campos do veredito. Ler o registro de revisão completo e confirmar que as afirmações e a evidência continuam lá.

**Cenários de aceitação**:

1. **Dado** uma resposta concluída, **quando** o revisor obtém `/v1/traces/{trace_id}/check`, **então** o corpo contém `trace_id`, `verdict`, `verdict_confidence` e `check_results`, e não contém o texto da resposta, fontes, afirmações, evidência nem valores de ferramenta.
2. **Dado** a mesma resposta, **quando** o revisor obtém `/v1/traces/{trace_id}`, **então** o registro de revisão inclui `claimed_statements`, `evidence`, `check_results`, `verdict` e `verdict_confidence`, além dos campos que já tinha.
3. **Dado** um `trace_id` que não é um UUID ou que nunca foi gravado, **quando** o revisor obtém a rota de check, **então** a resposta é não encontrado e nenhum corpo de registro é devolvido.
4. **Dado** a resposta de chat do lojista, **quando** ela é devolvida, **então** o corpo não muda por causa desta feature. O check não é acrescentado à resposta do chat.

---

### Casos de borda

- Uma recusa não afirma fato de produto nem de conta. Os três checks não se aplicam. O veredito é `unverified` e `verdict_confidence` é 0.
- Um handoff humano que não afirma fato de produto nem de conta é `unverified` do mesmo modo. Um handoff que ainda afirma um fato de produto ou de conta é checado como qualquer outra afirmação.
- Respostas de tempo e de câmbio são `unverified`. O serviço não guarda uma passagem Getnet recuperada nem um retorno de ferramenta de suporte para elas, então nenhum dos três checks se aplica. Elas não são marcadas `hallucinated` por terem fontes vazias.
- Um usuário desconhecido numa pergunta de conta, respondido como "registro não encontrado" com uma afirmação cujo `status` é `not_found` e que não afirma saldo, passa no check de payload da ferramenta. Uma afirmação que declara prazo de depósito ou valor para esse usuário desconhecido falha.
- Uma afirmação que falha faz a resposta falhar. Afirmações posteriores que passam não a limpam.
- Um check que não se aplica não faz a resposta falhar e não rebaixa um veredito que passou.
- BM25 e Chroma usam as mesmas regras. A evidência registra qual dos dois produziu a nota. A barra de manutenção não muda entre eles.
- Depois de reiniciar o processo o check não pode ser lido, porque o registro de revisão estava só em memória. Esse é o store de rastro atual, não uma falha nova.

## Requisitos *(obrigatório)*

### Requisitos funcionais

- **FR-001**: Toda resposta de produto ou de suporte que afirma um fato DEVE emitir uma lista de afirmações antes de o registro de revisão ser gravado. Cada afirmação DEVE nomear o que foi dito e suas citações. Citações de produto são URLs de fonte. Citações de suporte são nomes de ferramenta. O serviço NÃO DEVE derivar afirmações varrendo a prosa da resposta.
- **FR-002**: Quando nenhum modelo pago está configurado, o caminho de produto DEVE emitir uma afirmação por passagem que manteve, citando essa passagem, e o caminho de suporte DEVE emitir uma afirmação por campo que declarou, citando a ferramenta que chamou. Os mesmos três checks DEVEM rodar. Os testes DEVEM usar esse caminho e um modelo falso.
- **FR-003**: O check de âncora DEVE aplicar-se só a afirmações de produto. Ele passa só quando cada uma dessas afirmações cita uma fonte que foi recuperada para essa pergunta e cuja nota atende a barra de manutenção que a resposta de produto já usa: nota de pelo menos 0,15, e nota de pelo menos 94 por cento da melhor nota dessa pergunta. Caso contrário, falha. Não se aplica quando a resposta não tem afirmação de produto.
- **FR-004**: O check de payload da ferramenta DEVE aplicar-se só quando uma ferramenta de suporte rodou ou uma afirmação de suporte foi emitida. Ele passa só quando cada campo afirmado é igual ao retorno da ferramenta para o `user_id` da requisição. Os campos no escopo são `machine_model`, `pix_enabled` e `receiving_setup` em `get_merchant_account`; `status`, `sales_label`, `amount_brl` e `expected_deposit` em `get_receivables`; `status`, `symptom`, `machine_model` e `steps` em `diagnose_terminal`. Um campo afirmado que a ferramenta não devolveu falha. O check não se aplica quando nenhuma ferramenta de suporte rodou e nenhuma afirmação de suporte foi emitida.
- **FR-005**: O check de saída estruturada DEVE aplicar-se a toda resposta de produto ou de suporte da qual se espera um fato. Ele passa só quando a lista de afirmações não está vazia e cada citação está nas fontes desta resposta (produto) ou nas ferramentas invocadas desta resposta (suporte). Uma lista vazia numa resposta assim falha. O check não se aplica a uma recusa, a um handoff sem fato e a uma consulta pública geral.
- **FR-006**: Cada resultado de check DEVE ser exatamente um de `pass`, `fail` ou `not_applicable`.
- **FR-007**: O veredito DEVE ser `hallucinated` quando qualquer check aplicável falhou, `verified` quando pelo menos um check se aplicou e todos os aplicáveis passaram, e `unverified` quando nenhum check se aplicou.
- **FR-008**: `verdict_confidence` DEVE ser um número de 0 a 1, separado da confiança que a resposta já tem. DEVE ser 0 quando o veredito é `unverified`. DEVE ser 1 quando o veredito é `hallucinated` porque uma citação está ausente, a lista de afirmações está vazia ou um campo de ferramenta discorda. DEVE ser a distância da barra de manutenção até a nota citada, limitada ao intervalo de 0,01 a 1, quando a única falha é uma nota abaixo da barra. DEVE ser a menor nota de recuperação citada quando o veredito é `verified` e uma passagem foi citada, e 1 quando `verified` só com evidência de ferramenta.
- **FR-009**: O registro de revisão de toda resposta DEVE ganhar `claimed_statements`, `evidence`, `check_results`, `verdict` e `verdict_confidence`. Os campos de revisão que já existiam permanecem. O corpo da resposta de chat NÃO DEVE ganhar esses campos.
- **FR-010**: A evidência de produto DEVE registrar o título citado, o endereço público, o nome do retriever (`bm25` ou `chroma`) e a nota. A evidência de suporte DEVE registrar o nome da ferramenta, os nomes dos campos comparados e se coincidiram. A evidência de suporte NÃO DEVE registrar os valores dos campos. `amount_brl`, nomes legais e números de conta NÃO DEVEM ser gravados no registro de revisão, na resposta do check nem na linha de log.
- **FR-011**: Um check que falha DEVE marcar esse check como `fail` e o veredito como `hallucinated`. NÃO DEVE mudar a resposta do lojista, NÃO DEVE recusar uma resposta que o guardrail já aceitou e NÃO DEVE iniciar um segundo passe do guardrail.
- **FR-012**: `GET /v1/traces/{trace_id}/check` DEVE devolver só `trace_id`, `verdict`, `verdict_confidence` e `check_results` para uma resposta gravada, e DEVE devolver não encontrado para um `trace_id` desconhecido ou que não é UUID, sem corpo de registro. Esta é a única rota nova. O princípio V da constituição, versão 1.1.0, emendado em 2026-11-07, já permite esta rota e os campos de alucinação no registro de revisão. Nenhuma outra rota é adicionada. Nenhuma emenda adicional da constituição é necessária para esta feature.
- **FR-013**: Os resultados dos checks DEVEM ser gravados no mesmo registro de revisão em memória que o resto do rastro e DEVEM ser escritos na mesma linha JSON de log, sob as mesmas regras de redação. DEVEM desaparecer quando o processo reinicia. Um store durável não faz parte desta feature.
- **FR-014**: A suíte automática em `tests/` DEVE cobrir um passa e um falha para o check de âncora, o check de payload da ferramenta e o check de saída estruturada, mais a resposta enxuta do check e a ausência de `amount_brl` num check de recebíveis gravado. A suíte DEVE rodar com um modelo falso e sem acesso à rede. NÃO DEVE avaliar a redação da resposta.

### Entidades principais

- **Afirmação**: Uma asserção que o agente emitiu. Uma afirmação de produto tem o texto e uma ou mais URLs de fonte. Uma afirmação de suporte tem o nome da ferramenta e os nomes dos campos que declarou, sem valores de campo gravados.
- **Evidência**: O apoio que já estava em mãos para uma afirmação. Ou uma fonte pública recuperada (título, endereço, retriever, nota) ou uma comparação de ferramenta (nome da ferramenta, nomes dos campos, coincidiu ou não). Nunca um payload bruto do cliente.
- **Resultado de check**: Um dos três checks (`anchor`, `tool_payload`, `structured_output`) e seu status (`pass`, `fail`, `not_applicable`).
- **Veredito**: `hallucinated`, `verified` ou `unverified`, mais `verdict_confidence` de 0 a 1.
- **Resposta do check**: A leitura enxuta de um rastro: identificador, veredito, confiança e os três resultados de check.
- **Registro de revisão**: O registro por resposta que já existia, estendido com a lista de afirmações, a evidência, os resultados dos checks e o veredito. Continua local ao processo.

## Critérios de sucesso *(obrigatório)*

### Resultados mensuráveis

- **SC-001**: Na suíte repetível, o caso de âncora que passa passa, e o caso de âncora que falha falha (2 de 2).
- **SC-002**: Na suíte repetível, o caso de payload da ferramenta que passa passa, e o que falha falha (2 de 2), e o caso de falha gravado contém 0 cópias do valor das vendas.
- **SC-003**: Na suíte repetível, o caso de saída estruturada que passa passa, e o que falha falha (2 de 2).
- **SC-004**: Nesses seis casos, o veredito segue a regra: qualquer falha aplicável é `hallucinated`, e todos os passes aplicáveis são `verified` (6 de 6).
- **SC-005**: Um revisor consegue ler o resultado do check de uma resposta concluída em uma requisição, e essa resposta não contém texto da resposta ao lojista (0 campos de resposta).
- **SC-006**: A resposta de chat do lojista nesses casos tem a mesma forma de antes desta feature (0 campos de check acrescentados ao corpo do chat).
- **SC-007**: Recusa, handoff sem fato e as duas perguntas gerais (tempo e cotação do euro) são `unverified`, e não `hallucinated` (4 de 4).
- **SC-008**: A suíte que prova SC-001 a SC-007 roda sem serviço de linguagem pago e sem rede.

## Premissas

- A barra de manutenção é a que a resposta de produto já aplica: uma passagem só é citável quando a nota é de pelo menos 0,15 e de pelo menos 94 por cento da melhor nota dessa pergunta. Esta feature não escolhe um limiar novo.
- "O modelo emite afirmações" significa uma lista estruturada de afirmações nos caminhos de produto e de suporte. Quando o modelo está ausente, o fallback determinístico do FR-002 emite essa mesma lista a partir das passagens que manteve ou dos campos que declarou. A prosa nunca é analisada em busca de afirmações.
- Comparações de suporte são igualdade exata nos campos nomeados. Não se usa correspondência por paráfrase.
- `verdict_confidence` não substitui a confiança da resposta que o lojista já recebe.
- Quem chama a rota de check são os mesmos operadores que já podem ler um registro de revisão por `trace_id`. Nenhum login novo é acrescentado.
- O princípio II da constituição continua valendo. Comparar `amount_brl` em memória é permitido. Gravá-lo não é.
- O princípio V da constituição foi emendado em 2026-11-07 para a versão 1.1.0. Ele permite `GET /v1/traces/{trace_id}/check` e os campos de alucinação no registro de revisão. Essa emenda está feita.

## Fora de escopo

- Armazenamento durável de rastros ou de resultados de check. O comportamento no reinício continua o de hoje.
- Mudar, bloquear ou reescrever a resposta do lojista quando um check falha.
- Um painel, um alerta ou um segundo passe do guardrail.
- Checar respostas de tempo ou de câmbio. O serviço não guarda nota de passagem nem payload de suporte para elas.
- Recuperação nova, modelos novos, avaliação por paráfrase e qualquer métrica de alucinação que precise de dados que esta resposta ainda não tem.
