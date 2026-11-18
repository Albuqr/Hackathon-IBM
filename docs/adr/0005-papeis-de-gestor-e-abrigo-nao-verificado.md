# 0005 — Papéis de gestor e abrigo não verificado
status: accepted · date: 2026-11-18

## Context
A gestão de abrigos traz um perfil novo: quem coordena um abrigo registra o local, a capacidade, as pessoas que chegam e o estoque. Esse perfil precisa entrar sem convite (a crise não espera um admin aprovar), mas um abrigo recém-criado ainda não foi conferido por ninguém. A handoff também cita gestores regionais e de área, que ainda não serão construídos. O banco do Brasil precisa continuar unificável com o do Crisis (ADR 0002) e toda chamada do navegador passa pela `POLITICA` (ADR 0004).

## Options considered
| Option | Pros | Cons | Fit |
|---|---|---|---|
| Papel novo como valor de `users.role` (`gestor_abrigo`); verificação no abrigo | nenhuma tabela existente muda; `acesso.exige` e a `POLITICA` já funcionam por papel; merge sem mudança em `users` | papel é um só por conta (gestor não é também voluntário) | atende |
| Tabela de papéis (usuário ↔ vários papéis) | uma conta com vários papéis | altera o modelo de acesso inteiro e o merge; mais do que o protótipo pede | excesso |
| Verificação na conta do gestor | um selo só | um gestor com vários abrigos teria todos "confiáveis" de uma vez, inclusive o abrigo novo que ninguém viu | pior |
| Cadastro aberto para todos os papéis | uma tela só | ONG e admin passariam a se criar sozinhos; muda o que já existe | fora do escopo |

## Decision
- `gestor_abrigo` é um valor de `users.role`, sem mudar a tabela `users`. `gestor_regional` e `gestor_area` ficam reservados como valores futuros do mesmo campo; nada é construído para eles agora.
- Cadastro aberto (`POST /brasil/cadastro`, tela `/brasil/cadastro`) cria só `gestor_abrigo`; o papel não vem do corpo. Voluntário, ONG e admin continuam como estão.
- A verificação mora no abrigo (`abrigos.verificado`, `verificado_em`). O abrigo funciona assim que é criado e aparece como "Não verificado" até alguém verificar. Um gestor conta como verificado se qualquer abrigo dele estiver verificado (`abrigos.gestor_verificado`), o que amplia o que ele pode buscar.
- Ainda não existe quem verifique de verdade. Para testar, `POST /brasil/dev/abrigos/{id}/verificar` alterna o selo do próprio abrigo, só com `BRASIL_DEV_LOGIN=1`; sem isso responde 404 antes de qualquer outra checagem.
- Abrigo de outro gestor responde 404 (não revela que existe). Tabelas novas `abrigos` e `abrigo_crises` entram em `ORDEM`/`REFERENCIAS` do merge; `abrigo_crises` não tem `id` e tem as duas colunas como chave, remapeando `abrigo_id`.

## Consequences
Positivo: o papel novo cabe no acesso que já existe (uma linha na `POLITICA` por ação, a API confere papel e dono). O abrigo novo entra em operação na hora sem parecer oficial. Negativo: uma conta tem um papel só; no merge, um gestor cujo e-mail já exista no Crisis assume a conta (e o papel) do Crisis, como qualquer usuário (ADR 0002). Enquanto não houver verificação real, nenhum abrigo em produção fica verificado.
