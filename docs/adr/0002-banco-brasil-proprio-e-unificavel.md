# 0002 — Banco `brasil.db` próprio, unificável com o do Crisis
status: accepted · date: 2026-10-16

## Context
Testar sem sujar o banco do Crisis (FR-003) e poder unir os dados depois (FR-004, Q9).

## Options considered
| Option | Pros | Cons | Fit to NFRs |
|---|---|---|---|
| Arquivo SQLite separado, mesmo esquema + coluna `origem`, script de merge que renumera IDs e une usuários por e-mail | isolamento total; merge previsível; mesmo código de esquema | IDs inteiros colidem e precisam de renumeração | NFR-004, FR-003, FR-004 |
| Mesmo banco do Crisis, filtrando por `origem='brasil'` | sem merge | testes escrevem no banco real | fere FR-003 |
| IDs globais (UUID) no banco Brasil | merge sem renumerar | esquema diferente do Crisis (IDs INTEGER) | fere "mesmo esquema" |

## Decision
`brasil.db` separado (caminho em `BRASIL_DB_PATH`, recusado se igual a `DB_PATH`), esquema copiado do `init_db.py` + `origem`, e `merge_brasil.py` faz o merge em uma transação: usuários por e-mail, demais IDs inteiros renumerados, IDs texto de crises mantidos (já são únicos por fonte).

## Consequences
Positivo: o Crisis nunca é tocado até o merge. Negativo: mudanças futuras no esquema do Crisis precisam ser repetidas no esquema Brasil (o teste de merge acusa diferença).

## Sources
- [SQLite — ATTACH DATABASE](https://www.sqlite.org/lang_attach.html) · tier A · 2026-10-16
- [SQLite — Transactions](https://www.sqlite.org/lang_transaction.html) · tier A · 2026-10-16
