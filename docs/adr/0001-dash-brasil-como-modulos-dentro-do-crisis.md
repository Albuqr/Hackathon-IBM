# 0001 — Dash Brasil como módulos dentro do Crisis (blueprint + router)
status: accepted · date: 2026-10-16

## Context
O Dash Brasil precisa ser uma rota dentro do sistema (Q1), sem alterar o que existe além do mínimo (FR-001, FR-002, NFR-004).

## Options considered
| Option | Pros | Cons | Fit to NFRs |
|---|---|---|---|
| Flask Blueprint em `frontend/brasil/` + FastAPI `APIRouter` em `middleware/brasil/`, 1 linha de registro em cada app | mesma app e deploy; código novo isolado em pastas próprias | 2 linhas em arquivos existentes | NFR-004 (rotas atuais intactas) |
| Serviço separado no docker-compose | zero mudança no código existente | não é "dentro do sistema" (Q1 = c); outro deploy | fere Q1 |
| Rotas novas escritas dentro de `app.py`/`main.py` | nenhuma pasta nova | mistura código; diffs grandes em arquivos existentes | fere FR-001/FR-002 |

## Decision
Usar Blueprint (frontend) e APIRouter (API), registrados com 1 linha cada. O frontend do Dash Brasil fala só com a API `/brasil/...`; quem abre o `brasil.db` é só o router.

## Consequences
Positivo: tirar o Dash Brasil é apagar 2 pastas e 2 linhas. Negativo: a sessão Flask é compartilhada, então o login do Brasil usa chaves próprias (`br_user_id`, `br_role`) para não confundir IDs dos dois bancos.

## Sources
- [Flask — Modular Applications with Blueprints](https://flask.palletsprojects.com/en/stable/blueprints/) · tier A · 2026-10-16
- [FastAPI — Bigger Applications, Multiple Files (APIRouter)](https://fastapi.tiangolo.com/tutorial/bigger-applications/) · tier A · 2026-10-16
