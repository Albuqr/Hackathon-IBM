# Backlog da gestão de abrigos

Pendências da fatia 1 (`feat/brasil-abrigos`). Contexto em `WALKTHROUGH.md` e nas ADRs 0005 a 0008.

## 1. Tempo de guarda dos dados de quem saiu (bloqueio)
- **O quê:** definir por quanto tempo nome, nome da mãe, CPF e datas de quem saiu do abrigo ficam guardados, e
  implementar a regra (apagar ou anonimizar depois do prazo).
- **Por quê:** são dados pessoais de gente vulnerável (LGPD). Hoje nada é apagado.
- **Quem decide / o que destrava:** o cliente, sob a LGPD. **Bloqueia carregar qualquer dado real**; até lá só os dados
  fictícios da semente (`semear_teste.py`).

## 2. Curadoria de quase-duplicados na lista compartilhada de itens
- **O quê:** um jeito de unir ou renomear itens quase iguais ("agua" e "Água mineral") na lista `itens`, mantendo o
  estoque dos abrigos apontando para o item certo.
- **Por quê:** a lista cresce com itens criados por qualquer gestor; o agente `itens_duplicados` só sinaliza e nunca une
  (ADR 0007), então quase-duplicados podem se acumular e atrapalhar a soma por item.
- **Quem decide / o que destrava:** o João, ao definir quem faz a curadoria (papel novo ou admin) e como unir sem perder
  dados de outro abrigo. Adiado por decisão do João (2026-11-23).

## 3. CSRF na página de cadastro quando `fix/security-backlog` entrar
- **O quê:** `frontend/brasil/templates/brasil/cadastro.html` não estende `base.html`. Ao juntar a branch
  `fix/security-backlog` (CSRF), a página precisa de `{% csrf_token %}` no formulário e, no `<head>`, das duas linhas
  do `base.html` daquela branch (`<meta name="csrf-token" content="{{ csrf_value() }}">` e o `<script>` de
  `csrf.js`); e `cadastro.html` deve entrar em `FORMULARIOS` no `test_csrf.py` daquela branch.
- **Por quê:** com o CSRF em modo de bloqueio, o `POST` do cadastro sem o token responde 400 e ninguém consegue se
  cadastrar como gestor de abrigo.
- **Quem decide / o que destrava:** quem fizer o merge de `fix/security-backlog` com esta branch; não precisa de decisão
  de produto.
