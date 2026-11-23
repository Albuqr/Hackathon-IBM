# Decisões

Formato: data, decisão, motivo, como foi descoberto / o que deu errado.

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

## Pendências (não corrigidas)
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
