# 0006 — Dados de abrigados e escopo da busca
status: accepted · date: 2026-11-18

## Context
O gestor de abrigo registra quem chega e quem sai: nome, nome da mãe, CPF quando a pessoa sabe, entrada, saída, grupo familiar e necessidades especiais (idoso, deficiência, saúde, gestante). São dados pessoais de gente em situação vulnerável. Ao mesmo tempo, famílias se separam na crise e o gestor precisa achar alguém pelo nome, inclusive em outros abrigos. Abrigos novos nascem não verificados (ADR 0005), então qualquer pessoa pode se cadastrar como gestor; dar a ela busca em todos os abrigos logo no cadastro abriria os dados de todos. O banco segue unificável com o do Crisis (ADR 0002) e o navegador só chega à API pela `POLITICA` (ADR 0004).

## Options considered
| Option | Pros | Cons | Fit |
|---|---|---|---|
| Busca em todos os abrigos só para gestor com algum abrigo verificado; senão só nos próprios. CPF só de gente dos próprios abrigos | quem acabou de se cadastrar não varre ninguém; o gestor conferido ajuda a reunir famílias | enquanto não houver verificação real, ninguém busca fora dos próprios abrigos | atende |
| Busca sempre em todos os abrigos | mais simples, reúne famílias mais rápido | qualquer cadastro aberto lê nomes e CPFs de todos | inseguro |
| Busca sempre só nos próprios abrigos | nenhum dado sai do abrigo | não ajuda a achar quem está em outro abrigo | pouco útil |
| CPF obrigatório e com dígito verificador | identifica sem ambiguidade | muita gente chega sem documento; travar o cadastro na porta é pior | não serve |
| Busca com `lower()`/`LIKE` direto no nome | sem coluna extra | SQLite não tira acento: "joao" não acha "João" | não serve |

## Decision
- Tabelas novas `familias` (id, abrigo_id, criada_em, origem) e `abrigados` (id, abrigo_id, familia_id, nome, nome_mae, cpf, nome_busca, entrada_em, saida_em, necessidades JSON, origem), em `ORDEM`/`REFERENCIAS` do merge (famílias antes das pessoas, `abrigo_id` e `familia_id` remapeados). Nenhuma tabela existente muda.
- Uma chegada com duas ou mais pessoas cria uma família; uma pessoa sozinha fica sem família. Passar da capacidade não bloqueia: a resposta traz a lotação e um aviso. CPF repetido entre os presentes do mesmo abrigo também só avisa.
- CPF é opcional; a API guarda só os dígitos e exige exatamente 11 (não confere dígito verificador). Nome e nome da mãe são obrigatórios.
- `nome_busca` guarda o nome sem acento, minúsculo e com espaços simples (NFKD sem marcas combinantes), gravado na chegada. A busca pede pelo menos 2 letras, trata `%` e `_` como texto e devolve no máximo 50 resultados.
- Quem vê o quê: todas as rotas de pessoas exigem `gestor_abrigo` (voluntário, ONG e admin recebem 403, tanto na `POLITICA` quanto na API); pessoas de abrigo de outro gestor respondem 404. A busca devolve `escopo` (`meus_abrigos` ou `todos`), e cada resultado traz nome, nome da mãe, abrigo, entrada, saída e se está presente; a chave `cpf` só existe para gente dos próprios abrigos. A listagem de abrigos e o painel mostram só a contagem de presentes. Mapa, crises e rotas de voluntário/ONG/admin não leem `abrigados`.
- Nada de log: o módulo `abrigados.py` e a tela `pessoas.js` não imprimem nem logam dados de pessoas; as mensagens de erro citam a posição da pessoa ("Pessoa 2"), nunca o valor digitado.

## Consequences
Positivo: o gestor registra uma família inteira em uma chegada e acha alguém pelo nome sem se preocupar com acento; um cadastro aberto não expõe ninguém de fora do próprio abrigo, e o CPF nunca sai do abrigo onde a pessoa está. Negativo: sem verificação real, a busca em todos os abrigos só existe no teste (`BRASIL_DEV_LOGIN`); a busca por nome pode achar homônimos (o nome da mãe ajuda a distinguir); abrigos marcados como sensíveis ainda aparecem na busca de gestores verificados. Futuro: `gestor_regional` e `gestor_area` (ADR 0005) poderão buscar e ver lotação dos abrigos da sua região ou área, com a mesma regra de CPF; quem verifica abrigos e por quanto tempo os dados de quem saiu ficam guardados ainda precisa ser decidido.

## Sources
- [Python — unicodedata.normalize](https://docs.python.org/3/library/unicodedata.html#unicodedata.normalize) · tier A · 2026-11-18
- [SQLite — LIKE e ESCAPE](https://www.sqlite.org/lang_expr.html#like) · tier A · 2026-11-18
