# 0004 — Segredo da API, identidade encaminhada e encaminhador do Brasil
status: accepted · date: 2026-10-19

## Context
A porta da API está publicada (docker-compose `8001:8000`; as tools do watsonx gravam pelo IP público). A API do Crisis e a do Brasil aceitavam qualquer `user_id` no corpo, então quem alcançasse a porta agia como qualquer usuário, inclusive admin. No frontend do Brasil, ~17 rotas JSON rasas repetiam "pôr o usuário da sessão e checar papel" e discordavam da API sobre quem pode o quê (relatório de arquitetura, candidato 2). O dono pediu para corrigir no Brasil e no Crisis original, sem criar variável nova ("a chave já existe no .env").

## Options considered
| Option | Pros | Cons | Fit |
|---|---|---|---|
| Token derivado do `SECRET_KEY` (HMAC) exigido pela API; identidade em cabeçalho; papel lido do banco | sem variável nova; o valor bruto do `SECRET_KEY` nunca trafega; protege Crisis e Brasil de uma vez | quem chama precisa mandar o cabeçalho (frontend, bot, tools) | atende o pedido |
| Só fechar a porta no Easypanel | zero código | depende de config; não resolve a identidade no corpo; as tools do watsonx param | parcial |
| JWT por usuário | identidade assinada ponta a ponta | biblioteca e chave novas; mais código que o problema pede | excesso |

## Decision
- `middleware/seguranca.py`: com `SECRET_KEY` definido e diferente do padrão de dev, toda rota exige `X-Crisis-Token` = HMAC-SHA256(`SECRET_KEY`, "crisis-api-v1"). As exceções são `GET /` e `GET /brasil/saude`, e também `POST /save_events`, mas só na transição até as tools do watsonx serem republicadas; nessa rota, chamada sem token gera aviso no log. Sem `SECRET_KEY`, a API fica aberta e avisa na subida.
- API do Brasil: identidade em `X-Brasil-Usuario`, papel vindo do `brasil.db` e dono conferido na API (`middleware/brasil/acesso.py`). `user_id`/`org_id` do corpo não valem mais.
- Frontend do Brasil: o navegador só fala com `POST /brasil/acao/<nome>`. A tabela `POLITICA` (`frontend/brasil/encaminhador.py`) diz método, caminho e papéis de cada ação. O adapter da API vem de `app.config["BRASIL_API"]`.
- `python -m middleware.seguranca` imprime o token, para a conexão das tools no watsonx (variável `CRISIS_API_TOKEN`).

## Consequences
Positivo: a porta publicada deixa de dar acesso; a política de acesso do Brasil fica numa tabela com um teste por linha. Negativo: frontend, middleware e bot precisam do mesmo `SECRET_KEY`; as tools do watsonx precisam ser republicadas com o token antes de tirar a exceção do `/save_events`. Trocar o `SECRET_KEY` também desloga as sessões do Flask, porque é a mesma chave.

## Sources
- [Python — hmac](https://docs.python.org/3/library/hmac.html) · tier A · 2026-10-19
- [FastAPI — Middleware](https://fastapi.tiangolo.com/tutorial/middleware/) · tier A · 2026-10-19
