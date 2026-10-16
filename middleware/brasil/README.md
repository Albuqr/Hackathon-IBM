# Dash Brasil

Crises brasileiras por município, dentro do Crisis Monitor, em `/brasil/` (frontend) e `/brasil/...` (API).
Decisões: `docs/adr/0001` a `0003`. Requisitos: spec da feature `brasil-dash`.

## O que tem
| Parte | Onde |
|---|---|
| Rotas da API, banco `brasil.db`, ingestão, malha IBGE | `middleware/brasil/` |
| Páginas, mapa de pixels + coroplético, login de teste | `frontend/brasil/` |
| Fontes brasileiras (INPE, CEMADEN, INMET) | `tools/br_*.py` |

No código existente do Crisis mudou só 1 linha em `frontend/app.py` e 1 em `middleware/main.py` (registro dos módulos).

## Rodar local
```bash
python init_db.py                                   # banco do Crisis (se ainda não existe)
export BRASIL_DEV_LOGIN=1                           # liga os logins de teste
uvicorn middleware.main:app --port 8000 &
API_URL=http://localhost:8000 python frontend/app.py
```
Abra http://localhost:5000/brasil/ e entre por um dos links de teste (Voluntário, ONG, Admin).
No Admin, "Atualizar dados" faz a primeira ingestão (≈ 15 s).

## Configuração
| Variável | Padrão | Valores |
|---|---|---|
| `BRASIL_DB_PATH` | `brasil.db` ao lado de `DB_PATH` | caminho; não pode ser igual a `DB_PATH` |
| `BRASIL_DEV_LOGIN` | desligado | `1` liga `/brasil/dev-login/<voluntario/ong/admin>`. Nunca em produção. |
| `BRASIL_ORQUESTRADOR` | `local` | `local`, `watsonx`, `claude` |
| `BRASIL_INGESTAO_AUTO_MIN` | `0` (só manual) | `0` ou `15`–`1440` |
| `BRASIL_NOTIFICACOES` | `fila` | `fila` (nada sai; fila visível ao admin), `enviar` |
| `BRASIL_CLAUDE_MODELO` | `claude-sonnet-5-5` | id de modelo Claude |
| `ANTHROPIC_API_KEY` | — | segredo; só para `BRASIL_ORQUESTRADOR=claude` |
| `BRASIL_ORCHESTRATOR_AGENT_ID`, `BRASIL_PREDICTION_AGENT_ID` | — | IDs dos agentes `brasil_orchestrator` e `prediction_agent` publicados no watsonx (provedor `watsonx`) |
| `BRASIL_API_URL` | `http://localhost:8000` | URL da API que o `br_salvar_eventos` usa (provedor `watsonx`) |

Sem a credencial do provedor escolhido, tudo roda no `local` (regras, sem IA generativa) e o motivo aparece no log
e na resposta. O provedor `claude` precisa do pacote `anthropic` (`pip install anthropic`), que ainda não está em
`middleware/requirements.txt`.

## Orquestração e agentes
- `middleware/brasil/orquestracao/`: interface `Provedor` com `local`, `watsonx` e `claude`. Provedor novo = uma classe
  com `disponivel()` e `executar()`, registrada em `PROVEDORES` e em `config.ORQUESTRADORES`.
- Agentes novos: `agents/brasil_orchestrator.yaml` e `agents/brasil_news_agent.yaml` (os existentes não mudaram).
- Notícias: só os feeds e domínios de `fontes_noticias.yaml`. Crise de notícia entra como "não verificada", com
  severidade máxima 3, e sai em 7 dias se o admin não confirmar.

Valor inválido impede a API de subir, com mensagem que nomeia a variável.

## Testes
```bash
pip install pytest httpx                            # só para desenvolvimento
pytest                                              # unitários e de API, sem rede
# E2E no navegador (precisa de rede para Leaflet/fontes):
BRASIL_DB_PATH=data/brasil-e2e.db python -m middleware.brasil.semear_teste
# suba API e frontend com o mesmo BRASIL_DB_PATH e BRASIL_DEV_LOGIN=1, depois:
BASE_URL=http://localhost:5000 node --test frontend/brasil/tests/e2e/mapa.spec.mjs
```

## Malha
`dados/malha.json` = 5.570 municípios + 27 UFs (IBGE, malha "mínima") com população, área e densidade do Censo 2022,
gerado por `temp/mapa-brasil/scripts/build_mun.py`.
