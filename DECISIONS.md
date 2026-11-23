# Decisões

Formato: data, decisão, motivo, como foi descoberto / o que deu errado.

## Resumo executivo (fechamento da etapa, T8)
- **O que mudou:** `/ingest`, `/chat` e `/predictions` rodam sobre Claude (`middleware/llm.py`) sem watsonx Orchestrate, com saída validada, degradação (200 com `degradado: true`, nunca 500 por falha do provedor), teto diário de chamadas (500), limite por ciclo (30) e cache de `/predictions` só para resultado válido. A gravação em `crises` passa por `gravacao.py` (tipo validado).
- **O que não mudou:** matching, comunicação, otimização, Brasil (`middleware/brasil/`), frontend e a autenticação de `/save_events` (ADR 0004; isto mudou na T9, ver abaixo).
- **Estado:** suíte 596 passed (sem rede, sem chaves). `requirements.txt` do middleware instala e o app importa/responde numa imagem limpa (`Dockerfile.middleware`, `python:3.12-slim`), ver T8 abaixo. **Nenhuma chamada real à Anthropic foi feita**: qualidade das respostas, obediência ao formato JSON, ID do modelo e custo real seguem sem teste.
- **Para ir a produção:** `ANTHROPIC_API_KEY` e demais variáveis em `.env.example`; conferir fastapi/starlette no VPS; `/save_events` foi fechada na T9 (exige token; ver T9 no fim).

Índice: decisões e descobertas por data (abaixo, histórico preservado) · "T8: o que deu errado e como foi achado" · "T8: sem uso e condição para remover" · "T8: pendências" · "T8: ideias registradas" · "T8: riscos" · "T8: relatório /save_events".

## 2026-11-23 · Opção A para a orquestração sem watsonx
- **Decisão:** seguir a opção A (orquestração sem depender do watsonx).
- **Motivo:** tirar o caminho crítico de um provedor único e permitir rodar e testar sem rede.
- **Descoberta / o que deu errado:** nada de relevante até aqui.

## 2026-11-23 · Claude como primeiro provedor em llm.py
- **Decisão:** Claude é o primeiro provedor em `llm.py`; modelo pequeno por padrão, configurável por variável de ambiente.
- **Motivo:** custo e latência baixos para classificação e chat; trocar de modelo sem mexer no código.
- **Descoberta / o que deu errado:** nada de relevante até aqui.

## 2026-11-23 · Vários provedores = FUTURO
- **Decisão:** suporte a vários provedores fica como futuro; por ora só registro, sem implementação.
- **Motivo:** fora do escopo desta etapa.
- **Descoberta / o que deu errado:** n/a.

## 2026-11-23 · Embeddings = pontuação determinística
- **Decisão:** o matching continua com pontuação determinística. Não mexer no matching agora e não invalidar `volunteer_embeddings.npy`.
- **Motivo:** evitar regerar embeddings e mudar resultados de matching fora do escopo.
- **Descoberta / o que deu errado:** n/a.

## 2026-11-23 · Escopo da etapa
- **Decisão:** dentro: `/ingest`, `/chat`, `/predictions`, `classify_crisis`, `predict_humanitarian_risk`. Fora: matching, communication, optimization.
- **Motivo:** etapa enxuta, só o núcleo de ingestão, classificação e previsão.
- **Descoberta / o que deu errado:** n/a.

## 2026-11-23 · /save_events sem mudança de autenticação
- **Decisão:** a rota segue isenta de autenticação (ADR 0004); nada mudou na autenticação. O relatório fica para a T8.
- **Motivo:** mudar auth está fora desta etapa e quebraria o `tools/save_classification.py` em uso.
- **Descoberta / o que deu errado:** ver a decisão seguinte.

## 2026-11-23 · gravar_eventos como ponto único de escrita (T4)
- **Decisão:** `middleware/gravacao.py::gravar_eventos()` normaliza `crisis_type`/`type`, valida contra `TIPOS_CRISE` e rejeita tipo fora do schema por evento, sem derrubar o lote. `/save_event` e `/save_events` viraram adaptadores finos. A semântica INSERT/UPDATE foi mantida.
- **Motivo:** antes qualquer string era gravada em `crises.crisis_type`.
- **Descoberta / o que deu errado:**
  - Não havia lista única de tipos: README (7 tipos), prompt do `classify_crisis` (inclui `political`, sem `conflict`) e módulo Brasil (`geological`, `hydrological`). `TIPOS_CRISE` é a união dos 10 e precisa ser revista se o schema for oficializado.
  - Os testes de caracterização mostraram que `/save_events` devolvia 422 para JSON em lista: com `events: list` o FastAPI 0.165 tratava o parâmetro como formulário. O POST do `tools/save_classification.py` (`json=[payload]`) falharia. Corrigido com `List[dict]` (a versão do FastAPI não está fixada nos requirements).
  - Comportamento anterior: `crisis_type` não era normalizado, `type` era ignorado (caía em `humanitarian`) e `type` inválido era gravado como veio.
  - Ainda escrevem direto em `crises`, fora do `gravar_eventos`: `_ingest_fallback` (`middleware/main.py`), `middleware/brasil/ingestao.py` (INSERT e `expira_em`), `middleware/brasil/inteligencia.py` (UPDATE de verificação), `middleware/brasil/merge_brasil.py` (INSERT OR REPLACE). Não migrados nesta etapa.

## 2026-11-23 · T3: flask e requirements-dev.txt
- **Decisão:** criar `requirements-dev.txt` na raiz (middleware + tools + pytest + flask).
- **Motivo:** `flask` só estava em `frontend/requirements.txt`; a coleta da suíte falhou na 1ª rodada.
- **Descoberta / o que deu errado:** validado em venv novo: `pip install -r requirements-dev.txt` + pytest passa a suíte inteira.

## 2026-11-23 · FastAPI e starlette fixados
- **Decisão:** `middleware/requirements.txt` passa a fixar `fastapi==0.165.0` e `starlette==1.10.0` (versões em que a suíte passa, conforme `pip freeze` do .venv).
- **Motivo:** o tratamento de `events: list` como formulário mudou entre versões; sem fixar, o `/save_events` com JSON em lista pode voltar a dar 422.
- **Cobertura:** `middleware/tests/test_save_events.py::test_save_events_http_aceita_json_em_lista` (POST JSON em lista devolve 200).
- **Pendente:** conferir no VPS (`pip show fastapi starlette`) e alinhar com as versões fixadas.

## 2026-11-23 · Tipos dos produtores x TIPOS_CRISE (leitura de código, nada implementado)
Verificado só lendo o código. Produtores e tipos emitidos:
- USGS (`tools/fetch_usgs.py:51`, `middleware/main.py:555`): `seismic` (ok).
- GDACS no `_ingest_fallback` (`middleware/main.py:594-596,634`): seismic, meteorological, drought, wildfire; desconhecido vira `humanitarian` (ok).
- GDACS em `tools/fetch_gdacs.py:30-35,50`: seismic, meteorological, wildfire e `unknown` para eventtype fora do mapa (**rejeitado**).
- ReliefWeb (`tools/fetch_reliefweb.py:32-52`): meteorological, seismic, sanitary, wildfire, humanitarian (ok; padrão `humanitarian`). Não é usado pelo `_ingest_fallback`.
- EONET (`tools/fetch_eonet.py:5-10,59`): wildfire, meteorological, seismic, drought (ok; padrão `meteorological`).
- GDELT/conflitos (`middleware/main.py:714,741`; `tools/fetch_conflict_data.py:120,173`): `conflict` (ok).
- `classify_crisis` (`tools/classify_crisis.py:56,83`): o prompt lista meteorological, seismic, humanitarian, political, sanitary, wildfire, drought (todos válidos), mas a saída é texto livre do modelo, sem validação; o fallback usa `etype` de entrada, que pode ser `unknown` (do GDACS das tools) e seria **rejeitado**. O prompt não oferece `conflict`, `geological` nem `hydrological`.
- `save_classification` (`tools/save_classification.py:28,39`): repassa `classification["type"]` sem validar (padrão `humanitarian`); herda o risco do classificador.
- Bot do Telegram (`telegram_bot/bot.py`): só lê `crisis_type`; não grava em `crises` (posts em /user, /chat, associate-crisis).

Rejeições previstas: `unknown` (GDACS tools e fallback do classify_crisis) e qualquer valor livre do LLM fora da lista (ex. "flood", "earthquake").

Mapeamento proposto (não implementado):
| origem | valor | -> TIPOS_CRISE |
|---|---|---|
| GDACS tools | unknown | humanitarian (como o `_ingest_fallback` já faz) |
| GDACS tools | DR | drought (hoje meteorological; alinhar ao fallback) |
| LLM / classify_crisis | flood, storm, cyclone | meteorological (ou hydrological) |
| LLM / classify_crisis | earthquake, volcano | seismic |
| LLM / classify_crisis | epidemic, outbreak | sanitary |
| LLM / classify_crisis | fire | wildfire |
| LLM / classify_crisis | war, armed_conflict | conflict |
Sugestão: validar a saída do classify_crisis contra TIPOS_CRISE (valor fora vira `humanitarian` + `needs_review`) e adicionar `conflict` ao prompt.
Não verificado: respostas reais do modelo (sem rede/chaves), nem os valores de `type` que o ReliefWeb realmente devolve além do mapa, nem agentes/YAMLs do orchestrate que possam chamar `save_event(s)` com outros tipos.

## 2026-11-23 · _ingest_fallback usará gravar_eventos na T6
- **Decisão:** na T6 o `_ingest_fallback` (`middleware/main.py`) passa a gravar via `gravar_eventos`, saindo do INSERT direto. O módulo Brasil (`middleware/brasil/`) continua fora e segue gravando por conta própria.
- **Motivo:** ponto único de validação do tipo; os produtores acima já emitem tipos válidos no fallback.

## Pendências (não corrigidas) — lista da T3; versão atual em "T8: pendências"
- Aviso de depreciação `@app.on_event("startup")` em `middleware/main.py:94`.
- `starlette.testclient` pede `httpx2` no lugar de `httpx`.
- Versão do SDK do orchestrate diverge: README 2.8.0 x requirements 2.19.0.
- A suíte original não cobria o núcleo (`main.py`, tools).

## 2026-11-23 · T5: llm.py e agentes.py (substitutos futuros do call_orchestrate)
- **llm.py** é o único módulo que importa `anthropic` (import preguiçoso). Tipos neutros: `Mensagem`, `ChamadaFerramenta`, `ResultadoFerramenta`, `TurnoResultados`, `RespostaLLM`, `EspecFerramenta`; a conversão para `tool_use`/`tool_result` são funções puras dentro do módulo. Injeção: `definir_provedor(obj)` ou `completar(..., provedor=)`; `ProvedorFalso` fica em `middleware/tests/falsos.py`.
- **Dependências:** `anthropic==2.12.0` (instalada e testada no .venv) e `PyYAML==6.0.4` (já vinha transitivamente do orchestrate; agora explícita), ambas em `middleware/requirements.txt` (o requirements-dev já inclui via `-r`).
- **Modelo:** padrão `claude-haiku-5-5` (ID informado pelo ambiente; **não** validado contra a API). Trocar com `CRISIS_LLM_MODELO`; também `CRISIS_LLM_MAX_TOKENS` (1024) e `CRISIS_LLM_TIMEOUT` (30 s). Chave só em `ANTHROPIC_API_KEY`.
- **Exceções:** qualquer falha (rede, auth, rate limit, timeout, pacote ou chave ausentes) vira `LLMIndisponivel`, com só o nome da classe original na mensagem (sem vazar texto do SDK). `disponivel()` é False sem o pacote ou sem a chave, salvo provedor injetado.
- **agentes.executar** levanta `LLMIndisponivel` (o chamador decide fallback) e `AgenteNaoEncontrado`; estouro de `max_passos` (padrão 6 chamadas ao LLM) devolve `Resultado.erro`, sem levantar. Contexto é anexado à mensagem sob "Contexto:".
- **Tools sem o orchestrate (opção b):** `tools/*.py` não foram alteradas. O loader executa o arquivo com um stub temporário de `ibm_watsonx_orchestrate.agent_builder.tools.tool` em `sys.modules` (restaurado depois) e pega a função de mesmo nome. Escolhido porque um shim em `tools/_tool.py` tiraria o decorador real das tools publicadas pelo `import_all.py`.
- **Schema das tools:** derivado de assinatura, type hints e seção `Args:` da docstring (int/float/str/bool/list/dict; sem default = obrigatório). Limitação: tipos aninhados (`list[dict]`) viram só `array`/`object`; as tools de hoje só recebem escalares, então bastou.
- **Surpresa:** `classify_crisis` e `predict_humanitarian_risk` importam `ibm_watsonx_ai` (Granite no watsonx), que não está instalado nem em requirements do middleware. Sem o pacote elas ficam de fora do agente (aviso no log) e, com ele, ainda chamariam o watsonx, contrariando o objetivo. Na T6/T7 o classificador deve ser reescrito sobre `llm.completar` ou o agente deve classificar por conta própria. `save_classification` usa `VPS_API_URL` (rede) e `fetch_*` fazem rede: nos testes são substituídos via `executar(..., ferramentas={...})`.
- **Não verificado:** nenhuma chamada real à Anthropic (a conversão foi testada contra um cliente falso no formato do SDK); ID do modelo; comportamento com as tools reais em rede.

## 2026-11-23 · T6: /ingest sem watsonx
- **Fluxo:** `middleware/ingestao_crise.py::executar_ingestao(db, llm=None)`: coleta (a mesma do fallback, agora em `main._coletar_eventos`) -> `classificacao.classificar_evento` só para ids novos -> `gravar_eventos` em Python. O LLM não grava e não recebe ferramenta. `/ingest` não chama mais `call_orchestrate`; `get_wxo_token`/`call_orchestrate` ficam para o `/chat` (T7). Retorno: `ok`, `triggered_by` (`llm`, `llm+fallback` ou `fallback`), `cycle_id`, `crises_collected`, `crises_classified`, `crises_saved`/`events_saved`, `needs_review`, `skipped_existing`, `errors`, `degradado` (+ `motivo` quando degradado). Antes o `/ingest` devolvia só `ok`/`triggered_by` (o formato cycle_id/crises_* só existia no prompt de `agents/crisis_orchestrator.yaml`).
- **LLM indisponível (inclui teto diário):** o ciclo não falha; grava o que já foi classificado e manda o restante ao `_ingest_fallback(eventos)` (regras por fonte), com `degradado: true`. Risco: o GDACS RSS traz centenas de itens (197 na gravação, quase todos `WF`) e cada evento novo é uma chamada; o teto de 500/dia pode ser consumido em poucos ciclos. Não há limite por ciclo; fica como melhoria (filtrar por severidade da fonte antes de classificar).
- **`_ingest_fallback` agora usa `gravar_eventos(..., atualizar=False)`.** Antes só fazia INSERT; `gravar_eventos` faria UPDATE de severity/urgency/crisis_type em id existente, e a regra por fonte (ex. magnitude) sobrescreveria uma classificação melhor feita antes pelo LLM ou à mão. Mínimo seguro: parâmetro `atualizar` (padrão `True`, então `/save_event(s)` não mudam); o fallback e a ingestão nova só inserem ids ainda inexistentes. Efeito colateral aceito: tipo fora de `TIPOS_CRISE` agora é rejeitado e devolvido em `errors` (antes seria gravado). O aviso de Telegram foi extraído para `_avisar_novos` (sem mudar a lógica) e agora também cobre o caminho do LLM.
- **Deduplicação:** não existia na coleta. No fallback o `SELECT` antes do INSERT descartava a repetição dentro do lote; `gravar_eventos` sozinho trataria a repetição como UPDATE. `executar_ingestao` deduplica por `id` (primeiro vence) antes de classificar, para não pagar duas chamadas, e ignora ids já no banco.
- **Classificação (`middleware/classificacao.py`):** saída `{tipo, severidade 1-5, urgencia, confianca, justificativa, needs_review}`. Urgências permitidas (as que o código já usava): `immediate, 24h, 48h, 7days, monitoring`. Schema estrito: severidade inteira (bool, float e string rejeitados), `confianca` 0-1, tipo normalizado com o mapeamento proposto acima (`flood`->meteorological etc., `unknown`->humanitarian) e então validado contra `TIPOS_CRISE`. Tipo fora da lista é rejeitado com `log.warning` (id e valor, truncado) e nunca gravado. Qualquer saída inválida (JSON, campo ausente, faixa) vira `needs_review` conservador: confiança 0, tipo/severidade/urgência da própria fonte se válidos, senão `humanitarian`/2/`monitoring`; também com warning. Confiança < 0,7 marca `needs_review` (mesmo limiar da tool antiga). Não há coluna `needs_review` em `crises`: o evento é gravado com os valores da fonte e a contagem sai no retorno. O texto do evento vai como JSON dentro de `<evento_nao_confiavel>`, com `<` escapado (não dá para forjar o fechamento do bloco), título limitado a 300 e descrição a 1000 caracteres; o prompt de sistema diz que nada ali dentro é instrução.
- **`tools/classify_crisis.py` intocado** e ainda importa `ibm_watsonx_ai`: ele continua sendo publicado no watsonx via `import_all.py` e a nova função mora em `middleware/`, sem tocar no que está publicado. `predict_humanitarian_risk.py` também ainda importa `ibm_watsonx_ai`; fica para a T7. O mapeamento `unknown`->`humanitarian` foi aplicado só na camada nova; `tools/fetch_gdacs.py` continua emitindo `unknown`.
- **Teto diário (`llm.py`):** `CRISIS_LLM_LIMITE_DIARIO` (padrão 500), contador por dia UTC **em memória por processo**, com lock. Em memória porque é o mínimo que protege o custo contra laço/abuso sem criar armazenamento; reiniciar zera o contador e, com vários workers, o teto vale por worker (persistir em SQLite/Redis é futuro). Conta tentativas ao provedor, inclusive as que falham (também podem custar tokens e retry em laço é o risco típico). Estourou: `LLMIndisponivel` ("teto diário de N chamadas ao LLM atingido", sem dados do evento) sem chamar o provedor. Um provedor passado direto por `llm=` a `classificar_evento`/`agentes.executar` (como o `ProvedorFalso` dos testes) não passa pelo contador, que fica em `llm.completar`.
- **Fixtures (`middleware/tests/fixtures/`):** REAIS, gravadas em 2026-11-23 com `curl` e User-Agent genérico, sem e-mail nem dados do usuário, recortadas e com a primeira entrada repetida (a duplicata é inserida por nós; o resto é original): `usgs_4_5_day.real.geojson` (3 eventos + duplicata), `gdacs_rss.real.xml` (4 itens + duplicata; removidos os e-mails do cabeçalho), `gdacs_geteventlist.real.json` (3 + duplicata). SINTÉTICA: `reliefweb_disasters.sintetica.json`: a ReliefWeb v2 respondeu 403 ("You are not using an approved appname"), então foi construída à mão a partir da documentação v2 e do parser de `fetch_reliefweb.py`, com um tipo fora do mapa e um id repetido; nunca foi comparada com resposta real. Falta um appname aprovado para regravar.
- **Defeitos descobertos em `tools/fetch_gdacs.py` (não corrigidos; só caracterizados em `middleware/tests/test_fetchers.py`):** (1) `geteventlist/SEARCH` devolve GeoJSON, mas a tool faz `ET.fromstring` -> sempre devolve `[{"error": ...}]` com a resposta real; (2) mesmo com RSS, procura `geo:lat` direto no item e o RSS real aninha em `geo:Point`, então lat/lon saem 0. O `_ingest_fallback` usa o RSS (`xml/rss.xml`) com o caminho aninhado e está correto. Corrigir a tool altera o que está publicado no watsonx, por isso ficou fora.
- **Outras descobertas:** `tools/fetch_reliefweb.py` e GDACS-tool diferem no mapeamento de `DR` (meteorological x drought no fallback). Os fetch_* têm testes sem rede via `agentes._carregar_ferramenta` (contorna o decorador do watsonx).
- **Não verificado / falta:** nenhuma chamada real ao provedor (a qualidade da classificação com o modelo real e o ID `claude-haiku-5-5` seguem sem teste); EONET e GDELT sem fixture (nos testes falham de propósito, o código já trata); ReliefWeb real; custo real por ciclo; limite por ciclo; persistência do contador; `/chat` e `/predictions` (T7) e `predict_humanitarian_risk`.

## 2026-11-23 · Limite de classificação por ciclo
- **Decisão (dono):** `CRISIS_LLM_MAX_POR_CICLO` (padrão **30**; ausente, não numérica ou <= 0 vira 30, com `log.warning` quando foi definida). Em cada ciclo de `executar_ingestao`, só até N eventos **novos** (id ainda inexistente em `crises`) vão ao LLM. Complementa o teto diário (`CRISIS_LLM_LIMITE_DIARIO`): o diário protege o custo do dia, o por ciclo evita que um ciclo com centenas de itens (GDACS) consuma o dia inteiro.
- **Ordem:** mais recentes primeiro, pelo primeiro campo presente entre `date`, `published`, `event_date`, `created_at`, comparado como texto (ISO 8601). Hoje só o EONET traz `date`; USGS, GDACS, GDELT e os conflitos fixos não têm data no evento normalizado, então vão por último, na ordem da coleta (ordenação estável). Na prática o limite corta primeiro o que não tem data. Melhoria possível: propagar a data de USGS (`properties.time`) e GDACS (`pubDate`) em `_coletar_eventos`. Formatos de data mistos entre fontes comparam mal como texto; hoje só há um formato.
- **Excedente nunca é descartado:** vai ao `_ingest_fallback` (regras por fonte, só insere ids novos) e é gravado normalmente.
- **Como fica marcado para revisão (sem mudar schema):** `crises` não tem coluna de revisão, mas `classifications_log` (já existente em `init_db.py` e no módulo Brasil) tem `needs_review`. Cada evento do excedente ganha uma linha ali com `needs_review=1`, severidade/urgência/tipo gravados pela regra da fonte, `confidence` nulo e justificativa "Excedente do limite de classificação por ciclo...". Revisão = `SELECT crisis_id FROM classifications_log WHERE needs_review=1`. Falha ao gravar o log é só avisada (não derruba o ciclo). Obs.: o `needs_review` do LLM (confiança < 0,7 ou saída inválida) continua só no retorno e no log de aplicação, sem linha em `classifications_log`; unificar fica como melhoria.
- **Retorno:** `crises_classified` (classificados pelo LLM com confiança suficiente), `excedente_por_limite` (quantos foram ao fallback por causa do limite) e `needs_review` (do LLM, como antes). `excedente_por_limite` é distinto de `degradado` (LLM indisponível/teto diário) e os dois podem coexistir: então `degradado: true`, `motivo` preenchido e `excedente_por_limite > 0`. Só o excedente por limite é marcado em `classifications_log`; o que caiu por indisponibilidade não é (é transitório e já sinalizado por `degradado`). `triggered_by` vale `llm+fallback` se houve classificação e fallback, `fallback` se só fallback. `skipped_existing` conta só ids que já estavam no banco.
- **Limitação conhecida (comportamento atual):** o excedente gravado pelo fallback já existe no banco, então nos ciclos seguintes é tratado como id existente: **não é reclassificado** (INSERT-only, protege o teto) e fica com a regra por fonte até revisão manual. Testado (`test_ids_existentes_nao_sao_reclassificados_em_ciclos_seguintes`): no 2º ciclo com a mesma coleta, 0 chamadas ao LLM e nada gravado/atualizado.
- **Proposta, não implementada:** existe um jeito simples de distinguir o que foi gravado por fallback: o próprio `classifications_log` (`needs_review=1` e justificativa de excedente). Um ciclo poderia reclassificar até N desses ids por vez (os mais recentes), e então gravar com UPDATE, o que exige `gravar_eventos(atualizar=True)` apenas para esses ids e limpar/encerrar a marca (nova linha com `needs_review=0`). Não foi feito porque muda a regra "nunca sobrescrever" e precisa de decisão do dono sobre quando uma classificação manual deve ser preservada.
- **Não verificado:** comportamento com a coleta real em rede (EONET com `date`) e custo real por ciclo; nenhuma chamada real ao provedor.

## 2026-11-23 · T7: /chat e /predictions sem watsonx; Orchestrate fora do núcleo
- **/chat (`middleware/chat.py`, endpoint em `main.py`):** `context_type == "volunteer"` -> `volunteer_agent`; qualquer outro valor (ou ausente) -> `assistant_agent`, via `agentes.executar` (sem tools). **Contrato preservado:** entrada `text` ou `message` (+ `user_id`, `telegram_id`, `username`, `context_type`, que o frontend/bot enviam); saída `{"reply", "response"}` com o mesmo texto (o frontend lê `reply || response`; o bot idem). **Acrescentado:** `degradado` (bool) e, na entrada, `context` opcional. Mensagem vazia continua `"Mensagem vazia."` (sem LLM, `degradado=false`). Mudança: antes um erro interno devolvia o campo `error` com `str(e)` (vazava detalhe interno); agora não há `error` e a mensagem é fixa.
- **Degradação:** `LLMIndisponivel` (inclui teto diário), YAML ausente (`AgenteNaoEncontrado`), resposta vazia/`erro` do executor e qualquer exceção inesperada (`log.exception` com stack) -> **200**, `reply` = "O assistente está temporariamente indisponível. Tente novamente em alguns minutos.", `degradado=true`. Nunca 500 por falha do provedor.
- **Dados vs instrução:** a instrução do sistema vem só do YAML. A mensagem vai em `<mensagem_nao_confiavel>` e o `context` em `<contexto_nao_confiavel>` (este por `contexto=` de `agentes.executar`), ambos com `<` escapado (`&lt;`) para não forjar o fechamento, e com uma linha dizendo ao modelo que o bloco é dado. **Limitação:** o frontend (`/api/chat`) e o bot do Telegram NÃO usam o campo `context`; eles prefixam o contexto (perfil do voluntário, crises próximas) dentro de `text`, então esse contexto também fica dentro de `<mensagem_nao_confiavel>`. É aceitável (tudo é dado), mas o frontend não foi alterado para usar `context`. Os YAMLs (`assistant_agent`/`volunteer_agent`) ainda citam "llm: watsonx/..." e "Use the crisis context provided at the start of each message"; só `instructions` é lido.
- **Tamanho:** não havia limite. Novo `CRISIS_CHAT_MAX_CHARS` (padrão 6000, conta o contexto que o frontend/bot anexam); acima disso responde 200 "Mensagem muito longa..." sem chamar o LLM e sem `degradado`. Rejeita em vez de truncar para não cortar a pergunta real, que vem depois do contexto. O 6000 é um palpite: o prompt do bot com 5 crises não foi medido.
- **Previsão (`middleware/previsao.py::prever_risco(eventos, llm=None)`):** formato atual do tool (`tools/predict_humanitarian_risk.py`, intocado e ainda publicado no watsonx) preservado: `predictions[{location, country, risk_type, probability, timeframe, recommended_action, justification}]`, `analysis_timestamp`, `total_events_analyzed`. Acrescenta `timeframe_days` (int 7-30; `timeframe` continua `"N days"`) e `descartados`. Validação estrita: `risk_type` normalizado por `classificacao.normalizar_tipo_ingestao` (aliases + `TIPOS_CRISE`; o tool antigo não validava e o prompt só listava 6 tipos, agora 10), `probability` em `low|medium|high` (string, como já era; não há probabilidade numérica), horizonte inteiro 7-30, textos não vazios e truncados, máximo 10, ordenado alta -> baixa (o README já prometia). Item inválido: descartado com `log.warning` (índice e motivo), sem derrubar o lote. JSON inválido ou sem lista `predictions`: `predictions=[]` + `error`. Eventos (até 50, só id/title/country/severity/urgency/crisis_type/source, título a 300) em `<eventos_nao_confiaveis>` com `<` escapado; sem ferramentas. Sem eventos: não chama o LLM.
- **/predictions e o cache:** antes o cache gravava qualquer resultado (inclusive `{"error":..., "predictions": []}`, que é truthy, então um erro ficava servido por 1 h). Agora só entra no cache lista **não vazia** e sem erro (TTL 3600 s). Erro, `LLMIndisponivel`, exceção inesperada e resultado vazio (mesmo sem erro) não são cacheados: a chamada seguinte tenta de novo. Falha -> 200 `{"predictions": [], "error": "Previsões indisponíveis no momento.", "degradado": true}`. Se existe resultado válido anterior (mesmo expirado), é servido com `stale: true`, `degradado: true` e `error` (trivial: o cache já guarda o último válido; a cópia servida não altera o cache). Sem eventos no banco, o retorno antigo (`note`) foi mantido. Risco: cache em memória por processo e sem trava; requisições simultâneas com cache vazio chamam o LLM várias vezes (cada uma conta no teto diário).
- **Orchestrate fora do núcleo:** `get_wxo_token`, `call_orchestrate` e `_token_cache` saíram de `main.py` (movidos sem alteração para `middleware/orquestracao_wxo.py`). **Não foi possível apagar de vez:** `middleware/brasil/orquestracao/watsonx.py` faz `from middleware.main import call_orchestrate`, então `main.py` mantém um re-export com `# noqa`, sem alterar o Brasil. Nenhuma rota do núcleo usa. O teste `test_endpoint_nao_chama_orchestrate` virou `test_nucleo_nao_chama_orchestrate` (cobre /ingest, /chat e /predictions; o antigo só cobria /ingest e patchava o nome em `main`). `WO_API_KEY`/`WO_INSTANCE`/`*_AGENT_ID` não são mais lidas pelo núcleo; seguem lidas por `orquestracao_wxo.py` (Brasil, só se o provedor `watsonx` for escolhido) e por `test_agent.py`.
- **requirements.txt: nada removido.** `ibm-watsonx-orchestrate==2.19.0` continua necessário: `middleware/brasil/ingestao.py` (`fontes_padrao`) e `middleware/brasil/tests/test_fontes_br.py` importam `tools/*.py` com o decorador `@tool` real, e `middleware/tests/test_fetchers.py` carrega tools. `ibm-watsonx-ai` nunca esteve nos requirements. `agentes.py` usa o stub, então não depende do SDK. O SDK só sai do middleware quando o Brasil parar de importar as tools.
- **Sem uso no núcleo (nada apagado ou alterado; decisão do dono):**
  - `tools/classify_crisis.py` e `tools/predict_humanitarian_risk.py`: substituídos por `classificacao.py`/`previsao.py`; só restam como tools publicadas no watsonx (importam `ibm_watsonx_ai`, não instalado).
  - `tools/save_classification.py`, `tools/match_volunteers.py`, `tools/suggest_reallocation.py`, `tools/analyze_distribution.py`: nenhum código do middleware as importa (só existem para os agentes do watsonx).
  - Em uso (não são sobra): `tools/notify_telegram.py` (`main.py`), `tools/notify_whatsapp.py` (Brasil), `tools/fetch_*.py` e `tools/br_*.py` (Brasil `fontes_padrao`, `main` importa `fetch_eonet`, testes), `tools/br_salvar_eventos.py` (referenciado pelo Brasil).
  - `agents/*.yaml`: em uso pelo núcleo só `assistant_agent` e `volunteer_agent` (campo `instructions`). Sem uso no núcleo: `crisis_orchestrator`, `monitoring_agent`, `classification_agent`, `communication_agent`, `matching_agent`, `optimization_agent`, `prediction_agent` (/ingest e /predictions não os chamam mais; só o provedor watsonx do Brasil referencia alguns IDs). `brasil_*`: Brasil.
  - `import_all.py` (publica tools/agents no watsonx) e `test_agent.py` (chama o Orchestrate direto com `WO_*`): só fazem sentido enquanto o watsonx for mantido.
  - `middleware/orquestracao_wxo.py` e o re-export em `main.py`: só o provedor `watsonx` do Brasil.
  - `tools/requirements.txt` e o README (ainda descreve watsonx/Granite, `WO_*`, `predict_humanitarian_risk`): não atualizados.
- **Surpresas:** (1) o contador do teto diário é global e vazava entre arquivos de teste; cada arquivo que usa o provedor global precisa do reset (fixture local, como em `test_ingestao_crise.py`). (2) o cache antigo servia erro por 1 h. (3) o `/chat` antigo devolvia `str(e)` ao cliente.
- **Não verificado:** nenhuma chamada real ao provedor (qualidade do chat e das previsões, obediência ao formato JSON, ID do modelo); formatos reais do Telegram além do código lido (`telegram_bot/bot.py` envia `text` + `context_type`); tamanho real dos prompts do bot frente ao limite de 6000; instalação do `requirements.txt` em ambiente limpo (Docker).
- **Ideias, não implementadas:** frontend/bot passarem o contexto por `context`; trava anti-estouro no cache de `/predictions`; contador do teto persistente; retirar o provedor `watsonx` do Brasil para então remover `orquestracao_wxo.py` e o SDK.

## T8: o que deu errado e como foi achado
- **`/save_events` devolvia 422 com JSON em lista** (FastAPI 0.165 tratava `events: list` como formulário). Achado pelos testes de caracterização; corrigido com `List[dict]`; FastAPI e starlette fixados em `middleware/requirements.txt`; teste `test_save_events_http_aceita_json_em_lista`.
- **Cache de `/predictions` guardava erro por 1 h.** `{"error":..., "predictions": []}` é truthy, então entrava no cache. Achado lendo o código na T7; agora só lista não vazia e sem erro é cacheada.
- **`tools/fetch_gdacs.py` com dois defeitos** (geteventlist é GeoJSON mas a tool faz `ET.fromstring`; `geo:lat` procurado fora de `geo:Point`). Achados ao gravar fixtures reais (T6); só caracterizados em `middleware/tests/test_fetchers.py`, não corrigidos (a tool está publicada no watsonx).
- **`/chat` devolvia `str(e)` ao cliente** (detalhe interno vazando). Achado ao reescrever o `/chat` na T7; agora a mensagem é fixa e o stack vai só para o log.
- **Contador do teto diário vazava entre arquivos de teste.** O contador é global e vazava entre arquivos de teste. Achado na T7; cada arquivo que usa o provedor global reseta o contador por fixture local.
- **Limite por ciclo cortava primeiro os eventos sem data.** USGS, GDACS, GDELT e conflitos fixos não trazem data no evento normalizado; só o EONET traz `date`. Achado ao implementar a ordenação por data; documentado, não corrigido (propagar `properties.time` e `pubDate` é melhoria).
- **Fixtures reais x sintética.** USGS, GDACS RSS e GDACS geteventlist foram gravados da rede (2026-11-23). A ReliefWeb v2 respondeu 403 ("not using an approved appname"), então a fixture é sintética e nunca foi comparada com resposta real.
- **`flask` ausente na coleta da suíte** (só estava em `frontend/requirements.txt`): criado `requirements-dev.txt`.
- **Gravação direta em `crises` fora de `gravar_eventos`:** `middleware/brasil/ingestao.py`, `inteligencia.py` e `merge_brasil.py` seguem gravando por conta própria.
- **Imagem limpa (T8):** em `middleware/main.py` o import falha sem a pasta `data/` (`BRASIL_DB_PATH` exige diretório gravável, `middleware/brasil/config.py`); no `docker-compose.yml` o volume `./data:/app/data` resolve, mas `docker run` solto da imagem, sem volume, não sobe. Com `mkdir data` o app importa e `/chat` responde degradado.

## T8: sem uso e condição para remover
Nada foi apagado. Condições:
- `tools/classify_crisis.py`, `tools/predict_humanitarian_risk.py`: remover quando o dono decidir parar de publicar no watsonx (já substituídos por `classificacao.py` e `previsao.py`; importam `ibm_watsonx_ai`, que não está instalado).
- `tools/save_classification.py`, `match_volunteers.py`, `suggest_reallocation.py`, `analyze_distribution.py`: nenhum código do middleware as importa; só existem para os agentes do watsonx. Remover junto com o watsonx. `save_classification` ainda é o único chamador externo conhecido de `/save_events` (ver relatório).
- 7 YAMLs sem uso no núcleo (`crisis_orchestrator`, `monitoring_agent`, `classification_agent`, `communication_agent`, `matching_agent`, `optimization_agent`, `prediction_agent`): remover quando o provedor `watsonx` do Brasil deixar de referenciar IDs de agentes. Ficam `assistant_agent` e `volunteer_agent` (usados pelo `/chat`) e os `brasil_*`.
- `import_all.py` e `test_agent.py`: só fazem sentido enquanto o watsonx for mantido (publicam tools/agentes; chamam o Orchestrate com `WO_*`).
- `middleware/orquestracao_wxo.py` e o re-export `call_orchestrate` em `main.py`: `middleware/brasil/orquestracao/watsonx.py` importa `middleware.main.call_orchestrate`. Remover depois de retirar o provedor `watsonx` do Brasil.
- `ibm-watsonx-orchestrate==2.19.0` em `middleware/requirements.txt`: sai quando o Brasil e os testes pararem de importar `tools/*.py` com o decorador `@tool` real.

## T8: pendências
- Depreciação `@app.on_event("startup")` em `middleware/main.py` e `starlette.testclient` pedindo `httpx2` no lugar de `httpx` (a imagem limpa instala os dois).
- VPS: conferir `pip show fastapi starlette` contra as versões fixadas (0.165.0 / 1.10.0).
- ReliefWeb: o appname (`hktn26-crisis`, padrão em `tools/fetch_reliefweb.py`, sobrescrevível por `RELIEFWEB_APPNAME` desde a T9) foi recusado pela API v2; falta um appname aprovado para regravar a fixture real.
- Tipos e mapeamentos: `tools/fetch_gdacs.py` ainda emite `unknown` e `DR` como meteorological (o `_ingest_fallback` usa drought); `classify_crisis` sem validação; ver "Tipos dos produtores x TIPOS_CRISE".
- README: as seções de agentes e ferramentas ainda descrevem o watsonx (marcadas como legado); a divergência de versão do SDK (README 2.8.0 x requirements 2.19.0) foi corrigida na T8. `tools/requirements.txt` não foi revisado.
- Os YAMLs `assistant_agent`/`volunteer_agent` ainda citam "llm: watsonx/..." e "Use the crisis context provided..."; só `instructions` é lido.
- Frontend e bot não usam o campo `context` do `/chat` (colocam o contexto dentro de `text`).
- Excedente do limite por ciclo não é reclassificado; o `needs_review` do LLM não vira linha em `classifications_log`.
- `CRISIS_CHAT_MAX_CHARS=6000` é palpite; o prompt do bot com 5 crises não foi medido.
- `.env.example` é novo na T8 (antes o README mandava copiá-lo e ele não existia); o `docker-compose.yml` usa `env_file: .env`.

## T8: ideias registradas (não implementadas)
- Vários provedores de LLM (hoje só Anthropic, por trás da interface de `llm.py`).
- Teto diário persistente (SQLite/Redis); hoje é por processo, em memória, e zera ao reiniciar.
- Trava anti-estouro no cache de `/predictions` (requisições simultâneas com cache vazio chamam o LLM várias vezes).
- Frontend e bot passarem o contexto por `context` no `/chat`.
- Reclassificar o excedente do limite por ciclo, usando `classifications_log` (`needs_review=1`) para achá-lo.
- Propagar a data de USGS e GDACS em `_coletar_eventos`.
- Retirar o provedor `watsonx` do Brasil, para então remover `orquestracao_wxo.py`, o re-export e o SDK.

## T8: riscos
- **Sem validação real do provedor:** ID `claude-haiku-5-5` e o formato JSON das respostas nunca foram exercitados contra a API; a validação estrita rejeita saída ruim, mas a taxa de rejeição é desconhecida.
- **Custo:** teto de 500 chamadas/dia por processo (vários workers = teto por worker) e 30 por ciclo; o custo real por ciclo não foi medido.
- **API aberta sem `SECRET_KEY`:** sem o segredo (ou com o padrão de dev) toda a API fica aberta, com aviso na subida; `/save_events` é isento mesmo com segredo (ADR 0004).
- **Cache e contador em memória por processo:** reinício zera o contador do teto; cache de `/predictions` sem trava.
- **Dependência do legado:** o Brasil ainda importa `main.call_orchestrate` e as tools com decorador do watsonx; mexer nisso sem tirar o provedor `watsonx` quebra o Brasil.
- **Ordem do limite por ciclo:** hoje corta primeiro o que não tem data (ver acima), logo a seleção do que vai ao LLM não é por gravidade.

## T8: instalação em ambiente limpo (verificado)
`docker build -f Dockerfile.middleware` (python:3.12-slim) instalou todo o `middleware/requirements.txt` sem erro (fastapi 0.165.0, starlette 1.10.0, anthropic 2.12.0, ibm-watsonx-orchestrate 2.19.0). Dentro do contêiner, sem chaves e com `mkdir data`, `import middleware.main` funcionou, `GET /` deu 200 e `POST /chat` deu 200 com `degradado: true`. Imagem de teste removida. Não foi testado: `docker compose up` (frontend, bot, rede externa do Easypanel).

## T8: relatório /save_events (só leitura; nada implementado)
**(a) Quem chama `/save_event(s)`** (busca em todo o repo, incluindo frontend, bot, scripts, testkit e `.github`):
| Chamador | Onde | Estado | Token |
|---|---|---|---|
| `tools/save_classification.py` | `tools/save_classification.py:45` (`POST {VPS_API_URL}/save_events`, `json=[payload]`) | Código no repo; só roda quando o watsonx executa a tool publicada. Com o `/ingest` fora do Orchestrate, o fluxo `crisis_orchestrator` -> `classification_agent` -> `save_classification` deixou de ser disparado pelo núcleo; só roda se alguém ainda usar os agentes direto no watsonx | Manda `X-Crisis-Token` **só se** a variável `CRISIS_API_TOKEN` existir no ambiente da tool (`:47`); caso contrário vai sem cabeçalho. Não dá para saber, pelo repo, se a tool publicada tem a variável |
| `agents/classification_agent.yaml:63,100` | cita `save_classification` nas instruções e na lista de tools | só publicado no watsonx | indireto |
| `agents/crisis_orchestrator.yaml:29,40` | idem | só publicado no watsonx | indireto |
| `import_all.py:12` | publica `tools/save_classification.py` | script manual | n/a |
Sem chamadores em `telegram_bot/`, `frontend/*.py`, `frontend/brasil`, `middleware/brasil`, `testkit/`, `.github/workflows`, `check.py`, `debug_apis.py`, `test_agent.py`. No bundle da landing (`frontend/static/lp/assets/index-CVCDW_Tp.js`) só há texto descritivo citando `save_classification.py`, não chamada. `tools/br_salvar_eventos.py` chama `/brasil/eventos`, outra rota. Os endpoints existem em `middleware/main.py:429` (`/save_event`) e `:448` (`/save_events`). Não verificado: chamadores fora do repo (outros serviços, cron, scripts no VPS).

**(b) Como `seguranca.py` trata hoje:** com `SECRET_KEY` válido, toda rota exige `X-Crisis-Token`, exceto `GET /`, `GET /brasil/saude` e, na transição, `POST /save_events` (`middleware/seguranca.py:22`, tratado em `:57`: sem token passa e loga aviso). ADR 0004 diz que a exceção sai quando as tools forem republicadas com o token. `POST /save_event` (singular) **não** é isento: já exige o token. Sem `SECRET_KEY` (ou com o padrão de dev), tudo fica aberto. Teste: `middleware/tests/test_seguranca.py::test_save_events_aceito_sem_token_na_transicao_com_aviso`.

**(c) Se for fechada (exigir `X-Crisis-Token`, isto é, remover a rota de `TRANSICAO`):** quebra o `save_classification` publicado no watsonx se ele estiver sem `CRISIS_API_TOKEN` (passa a receber 401 e devolve erro ao agente); qualquer script externo no VPS que poste sem cabeçalho (não verificado). Nada no núcleo, no frontend, no bot nem nos testes (exceto o teste da transição) depende da isenção. Com `SECRET_KEY` ausente ou igual ao padrão a API segue aberta, então fechar só tem efeito em produção com segredo definido. "Exigir segredo em variável de ambiente" já é o modelo atual: o token é derivado de `SECRET_KEY` (`python -m middleware.seguranca` imprime o valor para pôr em `CRISIS_API_TOKEN` da tool); não há variável nova a criar.

**(d) Mudança mínima proposta:** (1) confirmar no watsonx que a tool publicada tem `CRISIS_API_TOKEN` com a saída de `python -m middleware.seguranca` (ou republicá-la com `import_all.py`) e conferir nos logs da API que não há mais o aviso "sem X-Crisis-Token" por um período; (2) então `middleware/seguranca.py`: esvaziar `TRANSICAO` (linha 22; o bloco `if chave in TRANSICAO` em `:57` vira código morto e pode sair); (3) `middleware/tests/test_seguranca.py`: trocar o teste de transição por um que espera 401 sem token e 200 com o token em `/save_events`; (4) atualizar o ADR 0004 (exceção removida). Risco: baixo no código (uma linha e um teste); o risco real é operacional, o de derrubar chamadores externos que ainda não mandam o token (a tool publicada e o que mais exista fora do repo). Alternativa sem risco: manter a isenção e, como o `/ingest` não depende mais da rota, só fechar quando a tool for aposentada junto com o watsonx.

## T9: /save_events fechada (2026-11-23)
- **O que mudou:** `TRANSICAO` esvaziada e o desvio morto removido de `middleware/seguranca.py`. Com `SECRET_KEY` válido, `POST /save_events` exige `X-Crisis-Token`: sem token 401, token errado 401, token válido 200 e grava. `POST /save_event` (singular) já exigia e continua exigindo; `GET /` e `GET /brasil/saude` seguem isentos; sem `SECRET_KEY` (ou com o padrão de dev) a API segue aberta. Teste: `middleware/tests/test_seguranca.py::test_save_events_exige_token_apos_fim_da_transicao`. ADR 0004 atualizado (histórico mantido).
- **Tool publicada no watsonx:** a tool `save_classification` publicada **ficou inválida**: sem `CRISIS_API_TOKEN` no ambiente dela passa a receber 401. Nada foi republicado no watsonx; o núcleo não depende dela (o `/ingest` grava por `gravacao.py`). Não foi verificado se a tool publicada tinha a variável.
