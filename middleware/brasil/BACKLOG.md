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

## 4. Link da marca no cabeçalho com altura menor que 44px no celular
- **O quê:** o link da marca no cabeçalho tem cerca de 25px de altura em 390px; as demais áreas de toque já têm 44px.
- **Por quê:** difícil de tocar com o dedo; achado na conferência final (T11).
- **Quem decide / o que destrava:** só ajuste de CSS; não precisa de decisão de produto.

## 5. Botões desabilitados com pouco contraste e rodapé em 12px
- **O quê:** botões desabilitados ficam com contraste baixo e o texto do rodapé usa 12px.
- **Por quê:** acessibilidade (legibilidade para quem usa o celular ao ar livre ou tem baixa visão).
- **Quem decide / o que destrava:** ajuste de CSS; confirmar com o design os valores de cor e tamanho.

## 6. Zoom do mapa sobrepõe "Crises visíveis"
- **O quê:** os botões de zoom do mapa ficam por cima do bloco "Crises visíveis".
- **Por quê:** esconde parte da informação e do controle.
- **Quem decide / o que destrava:** ajuste de layout do mapa; não precisa de decisão de produto.

## 7. Nota no PRODUCT.md sobre a exceção do "Urgente"
- **O quê:** registrar em `PRODUCT.md` que o "Urgente" do estoque é uma exceção deliberada à regra visual dos demais estados.
- **Por quê:** sem a nota, a exceção parece um erro de estilo e pode ser "corrigida" por engano.
- **Quem decide / o que destrava:** o João confirma o texto da nota.

## 8. Node 24 falha quando a pasta de testes inteira roda
- **O quê:** com Node 24, `node --test` apontando para a pasta toda falha; rodar o arquivo `e2e/app.spec.mjs` direto funciona.
- **Por quê:** quem rodar os testes de tela pela pasta vê falha que não é do código.
- **Quem decide / o que destrava:** investigar o comportamento do Node 24 ou fixar o comando no README.
