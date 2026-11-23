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

## Pendências (não corrigidas)
- Aviso de depreciação `@app.on_event("startup")` em `middleware/main.py:94`.
- `starlette.testclient` pede `httpx2` no lugar de `httpx`.
- Versão do SDK do orchestrate diverge: README 2.8.0 x requirements 2.19.0.
- A suíte original não cobria o núcleo (`main.py`, tools).
