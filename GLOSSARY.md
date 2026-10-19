# Glossário

- **Crise**: evento de desastre ou humanitário registrado na tabela `crises`, com severidade 1–5, urgência, tipo e fonte.
- **Crise BR**: crise do Dash Brasil, gravada no `brasil.db`, com coordenadas dentro do contorno do Brasil e código IBGE do município.
- **Dash Brasil**: as páginas `/brasil/...` do frontend e as rotas `/brasil/...` da API.
- **Município**: unidade territorial do IBGE, identificada pelo código de 7 dígitos.
- **Foco de calor**: ponto detectado por satélite pelo INPE; não é incêndio confirmado.
- **Crise não verificada**: crise que veio de notícia (brasil_news_agent) e ainda não foi confirmada por um admin; severidade máxima 3.
- **Ingestão**: coleta das fontes, classificação e gravação das crises.
- **Orquestrador / provedor**: quem executa os agentes: `local` (regras, sem LLM), `watsonx` ou `claude`.
- **Origem**: coluna que marca de qual sistema veio um registro (`brasil`), usada no merge com o banco do Crisis.
- **Alerta de área**: crise com mais de um município em `municipios_afetados` (ex.: aviso do INMET); no mapa é um marcador só, e a área aparece ao abrir o popup.
- **Visão do mapa**: module puro (`frontend/brasil/static/visao.js`) que recebe as crises e os filtros e devolve o que desenhar (visíveis, números, pixels acesos). Marcadores, pixels e barra lateral só desenham a saída dele.
- **Encaminhador**: rota única `/brasil/acao/<nome>` do frontend do Brasil; aplica a tabela `POLITICA` e leva a ação à API com a identidade da sessão.
- **Segredo da API**: token `X-Crisis-Token` derivado do `SECRET_KEY` (ADR 0004) que a API exige de quem a chama.
