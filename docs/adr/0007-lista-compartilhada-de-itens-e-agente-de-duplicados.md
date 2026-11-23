# 0007 — Lista compartilhada de itens e agente de duplicados
status: accepted · date: 2026-11-18

## Context
Cada abrigo precisa dizer o que falta e o que sobra (status Urgente/Precisa/OK/Sobrando e quantidade aproximada) para quem vai abastecer. Se cada gestor digitar texto livre, "Água", "agua" e "Água mineral" viram três coisas e ninguém consegue somar a necessidade de uma região. A lista também não pode ser fechada: numa crise aparecem itens que ninguém previu. Profissionais (equipe de saúde, bombeiros, polícia) e veículos não são estoque: o abrigo só pede. O banco continua unificável com o do Crisis (ADR 0002), a orquestração é trocável (ADR 0003) e toda chamada passa pela `POLITICA` (ADR 0004).

## Options considered
| Option | Pros | Cons | Fit |
|---|---|---|---|
| Lista compartilhada que cresce (`itens`), nome normalizado único, item novo com grupo e unidade; parecidos só sinalizados | todos os abrigos falam do mesmo item; nada trava o gestor; dá para somar por item depois | ainda podem nascer quase-duplicados (sinalizados, não impedidos) | atende |
| Catálogo fixo mantido por admin | sem duplicados | trava a crise esperando alguém cadastrar o item | fora |
| Texto livre por abrigo | zero regra | não soma nem compara entre abrigos | fora |
| Unir duplicados automaticamente (regra ou LLM) | lista mais limpa | erro de união some com dados de outro abrigo; ninguém confere | arriscado |

## Decision
- Tabelas `itens` (nome, `nome_busca` UNIQUE, grupo, unidade, `so_necessidade`, `criado_por`) e `abrigo_itens` (abrigo, item, status, quantidade, `atualizado_em`). Grupos fixos: Sustento, Profissionais, Energia e Mobilidade, Estrutura e Ativos. A lista base entra no esquema com `INSERT OR IGNORE` (idempotente).
- `nome_busca` = nome sem acento, minúsculo, sem pontuação. Criar um item com o mesmo `nome_busca` devolve o que existe (`existente: true`), sem criar outro.
- `so_necessidade`: Profissionais sempre; em Energia e Mobilidade a pessoa diz se é veículo; Sustento e Estrutura nunca. Item só pedido aceita apenas Urgente/Precisa e exige quantos precisa (> 0); senão 422 com a mensagem em português.
- Duplicados: agente `itens_duplicados` no provedor `local` de `orquestracao`, chamado por `orquestracao.executar`. A regra (`estoque.duplicados`) compara sem acento e sem plural simples, sinaliza igual, um contido no outro, um começo do outro ou `difflib` ≥ 0,8. Só sinaliza ("Possível duplicado de: Água", com botão para usar o existente); nunca une nem renomeia. O watsonx responde indisponível para agente sem ID e o claude falha sem `agents/<agente>.yaml`, então os dois caem para o local. Um LLM pode assumir o agente depois, com a mesma interface.
- Merge: `itens` e `abrigo_itens` entram em `ORDEM`/`REFERENCIAS`; item cujo `nome_busca` já existe no Crisis é reaproveitado (`CHAVE_NATURAL`) e o estoque passa a apontar para o id de lá.
- Rotas `/brasil/itens/...` e `/brasil/abrigos/{id}/estoque...` só para `gestor_abrigo`; abrigo de outro gestor responde 404 (ADR 0005). Tela `/brasil/abrigo/<id>/estoque`: primeiro o que precisa agora, depois "Que item?" com sugestões ao digitar, depois a lista por grupo.

## Consequences
Positivo: um item novo criado num abrigo aparece para todos ao digitar; dá para somar necessidades por item entre abrigos depois. A regra roda sem rede e sem credencial. Negativo: quase-duplicados ainda podem ser criados de propósito e a lista não tem quem a limpe (falta um papel de curadoria). A regra é por texto: não sabe que "Gasolina comum" e "Gasolina aditivada" são itens diferentes que valem a pena manter (só avisa). Com outro orquestrador configurado, cada busca registra no log que caiu para o local.

## Sources
- [Python — unicodedata.normalize](https://docs.python.org/3/library/unicodedata.html#unicodedata.normalize) · tier A · 2026-11-18
- [Python — difflib.SequenceMatcher](https://docs.python.org/3/library/difflib.html#difflib.SequenceMatcher) · tier A · 2026-11-18
- [SQLite — UPSERT](https://sqlite.org/lang_upsert.html) · tier A · 2026-11-18
