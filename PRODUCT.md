# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
- **Voluntário(a)** brasileiro(a): quer ajudar em crises perto de onde mora, com as habilidades que tem (primeiros socorros, logística, resgate…). Chega pelo celular ou desktop, muitas vezes pela primeira vez, e precisa saber o que fazer agora: completar o perfil, escolher onde ajudar, responder convites de ONGs.
- **ONG**: coordena a resposta a uma crise. Precisa montar uma campanha (qual crise, de que precisa, quem convidar), acompanhar quem aceitou e encerrar.
- **Admin** da plataforma: rotina diária de operação: atualizar os dados das fontes, confirmar ou descartar crises que vieram de notícias, conferir a distribuição de voluntários e a fila de notificações.

## Product Purpose
Crisis Monitor Brasil mostra, num mapa, as crises brasileiras ativas (queimadas do INPE, riscos hidrológicos do CEMADEN, avisos do INMET, notícias de fontes confiáveis e fontes globais filtradas para o Brasil) e liga voluntários e ONGs a elas. Sucesso: o voluntário se inscreve onde é mais útil, a ONG monta a campanha com as pessoas certas, o admin mantém os dados confiáveis.

## Positioning
Crises separadas por evento (não agregadas por município), vindas de fontes oficiais brasileiras e verificadas por um admin quando vêm de notícia, com matching por habilidade, distância e disponibilidade.

## Operating Context
Parte do Crisis Monitor (hackathon UNASP + IBM), em `/brasil/...`. Flask + Jinja no frontend, FastAPI na API, SQLite próprio (`brasil.db`). Três perfis com login; logins de teste por perfil. Deploy no Easypanel. Telegram/WhatsApp em fila enquanto o Telegram estiver fora. Assistente de IA (orquestrador `local`, watsonx ou Claude) no chat do voluntário e no planejamento da campanha.

## Capabilities and Constraints
- Mapa (tela própria): um mapa, modos Municípios e Pixels, filtros, popup por crise. Fica como está nesta rodada.
- Fora do mapa: perfil, crises no raio, convites, painel da ONG, nova campanha, página da campanha (convidar, remover, editar, matching, notificar, encerrar, chat), admin, previsões.
- Toda chamada passa pelo encaminhador `/brasil/acao/<nome>` (tabela de política); identidade sempre da sessão.
- Interface em português do Brasil. Tema claro e escuro.

## Brand Commitments
- Nome: Crisis Monitor · selo BRASIL.
- Cor da marca: verde (`#0f5c3e` no claro) como a única cor de ação/destaque (decisão do Albuqr, 2026-10-19).
- Referência visual vinculante para as páginas fora do mapa: Apple "white gallery vitrine" (Refero Styles), com o verde da marca no lugar do azul.

## Evidence on Hand
Dados reais das fontes (centenas de crises por coleta), usuários de teste por perfil, nenhum depoimento, logo, foto ou número de impacto real: não inventar.

## Product Principles
1. Mostrar primeiro o que a pessoa precisa fazer agora; o resto espera.
2. Uma etapa por vez: concluir uma revela a próxima.
3. Fonte e verificação sempre visíveis: crise de notícia não verificada nunca parece oficial.
4. Nada inventado: números, nomes e crises vêm do sistema.
