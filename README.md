[🇧🇷 Português](#português) | [🇺🇸 English](#english)

---

# Crisis Monitor — HKTN26

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![Flask](https://img.shields.io/badge/Frontend-Flask-black?logo=flask)
![FastAPI](https://img.shields.io/badge/Middleware-FastAPI-009688?logo=fastapi)
![IBM watsonx](https://img.shields.io/badge/AI-IBM%20watsonx-052FAD?logo=ibm)
![Docker](https://img.shields.io/badge/Infra-Docker-2496ED?logo=docker)
![Telegram](https://img.shields.io/badge/Bot-Telegram-26A5E4?logo=telegram)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Português

### Índice

1. [Visão Geral](#visão-geral)
2. [Diagrama de Arquitetura](#diagrama-de-arquitetura)
3. [Stack Tecnológica](#stack-tecnológica)
4. [Agentes de IA](#agentes-de-ia)
5. [Ferramentas](#ferramentas)
6. [Funcionalidades por Perfil](#funcionalidades-por-perfil)
7. [Schema do Banco de Dados](#schema-do-banco-de-dados)
8. [Referência da API](#referência-da-api)
9. [Instalação](#instalação)
10. [Bot Telegram](#bot-telegram)
11. [Fontes de Dados Externas](#fontes-de-dados-externas)
12. [Variáveis de Ambiente](#variáveis-de-ambiente)
13. [Licença](#licença)

---

### Visão Geral

**Crisis Monitor** é uma plataforma de inteligência humanitária desenvolvida para o **Hackathon UNASP + IBM HKTN26**. O sistema resolve um problema crítico na resposta a desastres: a **coordenação descentralizada entre voluntários, ONGs e dados de crise em tempo real**.

Quando uma crise eclode — um terremoto, conflito armado, enchente ou surto epidêmico — a resposta humanitária frequentemente falha não por falta de voluntários, mas por falta de coordenação. Voluntários dispostos não sabem onde são mais necessários. ONGs não conseguem mobilizar as habilidades certas no lugar certo. Dados de múltiplas fontes internacionais ficam dispersos e sem tratamento.

O Crisis Monitor resolve isso com:

- **Ingestão automática** de dados de 5 fontes internacionais (USGS, GDACS, NASA EONET, GDELT, ReliefWeb) em tempo real
- **Pipeline de IA** com IBM watsonx Orchestrate e IBM Granite 3.3-8B para classificar, priorizar e fazer matching entre crises e voluntários
- **Plataforma web** com mapas interativos e dashboards diferenciados por perfil (Voluntário, ONG, Admin)
- **Bot Telegram** para alertas automáticos e inscrição em missões diretamente pelo celular
- **Previsão preditiva** de riscos humanitários futuros com horizonte de 7 a 30 dias

---

### Diagrama de Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         USUÁRIOS EXTERNOS                               │
│   Navegador Web          Bot Telegram          APIs Externas            │
└──────────┬───────────────────┬───────────────────────┬──────────────────┘
           │                   │                       │
           ▼                   ▼                       │
┌──────────────────┐  ┌────────────────────┐          │
│  Landing Page    │  │   Telegram Bot     │          │
│  (React/Vite)    │  │   python-telegram- │          │
│  Flask-served    │  │   bot + job-queue  │          │
└────────┬─────────┘  └────────┬───────────┘          │
         │                     │                      │
         ▼                     ▼                      │
┌────────────────────────────────────────┐            │
│        Flask Frontend (port 5000)      │            │
│  - Jinja2 templates (mapa, dashboard)  │            │
│  - Auth (sessão, hash SHA-256)         │            │
│  - Roteamento por perfil               │            │
│  - Proxy de API para middleware        │            │
└────────────────┬───────────────────────┘            │
                 │                                    │
                 ▼                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│              FastAPI Middleware (port 8000)                            │
│  - REST API completa (40+ endpoints)                                   │
│  - Ingestão de dados + pipeline de IA via watsonx Orchestrate          │
│  - Previsão preditiva com Granite                                      │
│  - Banco de dados SQLite                                               │
│  - Startup automático: backfill de link_codes                          │
└────────┬──────────────────────────────────────────┬────────────────────┘
         │                                          │
         ▼                                          ▼
┌───────────────────────┐              ┌────────────────────────────────┐
│  SQLite (crisis.db)   │              │  IBM watsonx Orchestrate       │
│  - users              │              │  (br-sao region)               │
│  - crises             │              │                                │
│  - missions           │              │  ┌──────────────────────────┐  │
│  - matches            │              │  │  crisis_orchestrator     │  │
│  - crisis_associations│              │  │  ├── monitoring_agent    │  │
│  - campaigns          │              │  │  └── classification_agent│  │
│  - campaign_volunteers│              │  ├── matching_agent         │  │
│  - telegram_subscribers              │  ├── communication_agent    │  │
└───────────────────────┘              │  ├── optimization_agent     │  │
                                       │  ├── prediction_agent       │  │
                                       │  ├── volunteer_agent        │  │
                                       │  └── assistant_agent        │  │
                                       │                              │  │
                                       │  IBM Granite 3.3-8B Instruct│  │
                                       │  IBM Granite Embedding 278M │  │
                                       └──────────────────────────────┘  │
                                                                         │
┌────────────────────────────────────────────────────────────────────────┘
│   FONTES DE DADOS EXTERNAS (consumidas pelos tools / middleware)
│   ├── USGS  — terremotos em tempo real (GeoJSON)
│   ├── GDACS — desastres naturais globais (RSS/XML)
│   ├── NASA EONET — incêndios, tempestades, vulcões (JSON)
│   ├── GDELT Events v2 — conflitos armados (CSV zip, 15 min)
│   └── ReliefWeb (ONU/OCHA) — desastres humanitários (REST API)
└────────────────────────────────────────────────────────────────────────
```

---

### Stack Tecnológica

| Camada | Tecnologia | Detalhes |
|--------|-----------|---------|
| **Frontend** | Flask 3.x + Jinja2 | Servidor Python renderizando HTML/CSS/JS |
| **Landing Page** | React + Vite (pré-compilada) | Bundle estático servido pelo Flask |
| **Mapas** | Leaflet.js + Stadia Maps | Tiles de satélite/rua com marcadores de crises |
| **Middleware** | FastAPI + Uvicorn | API REST assíncrona, Python 3.12 |
| **Banco de Dados** | SQLite 3 | Arquivo único `data/crisis.db`, compartilhado via volume Docker |
| **IA — Orquestração** | IBM watsonx Orchestrate 2.8.0 | Pipeline de agentes, região `br-sao` |
| **IA — Modelos** | IBM Granite 3.3-8B Instruct | Classificação, chat, previsão |
| **IA — Embeddings** | IBM Granite Embedding 278M Multilingual | Matching semântico de voluntários |
| **Bot** | python-telegram-bot 20.x + job-queue | Long-polling, alertas automáticos a cada 30 min |
| **Notificações** | Telegram Bot API + Twilio (WhatsApp) | Twilio ativado apenas para severity ≥ 4 |
| **Containerização** | Docker + Docker Compose | 3 serviços: `middleware`, `frontend`, `bot` |
| **Deploy** | Easypanel + Traefik | HTTPS automático via Let's Encrypt |

---

### Agentes de IA

Todos os agentes são do tipo `native`, usam o modelo `watsonx/ibm/granite-3-8b-instruct` com estilo ReAct/default, e são registrados no IBM watsonx Orchestrate.

#### `crisis_orchestrator`
Agente supervisor do pipeline de ingestão de dados. Coordena o ciclo completo: delega coleta de dados ao `monitoring_agent`, coleta classificações do `classification_agent` para cada evento, salva os resultados via API do VPS e retorna um relatório JSON estruturado com contagens e erros. **Não é usado para chat com usuários.**

Colaboradores: `monitoring_agent`, `classification_agent`

---

#### `monitoring_agent`
Especialista em coleta, normalização e deduplicação de dados de crises globais. Monitora 5 fontes simultâneas (ReliefWeb, GDACS, USGS, NASA EONET, GDELT/conflitos). Normaliza eventos heterogêneos para formato JSON unificado com coordenadas geográficas, tipo, fonte, data UTC e estimativa de afetados. Realiza deduplicação baseada em proximidade geográfica (raio 50 km) + mesmo tipo + janela de 24 horas.

Tools: `fetch_reliefweb`, `fetch_gdacs`, `fetch_usgs`, `fetch_conflict_data`

---

#### `classification_agent`
Classifica eventos brutos usando IBM Granite 3.3-8B com prompts few-shot calibrados em português e inglês. Atribui severidade 1–5, urgência (immediate/24h/48h/7days/monitoring) e tipo de crise. Usa o princípio da precaução: em caso de dúvida entre dois níveis, escolhe o mais alto. Salva classificações no banco via `save_classification`.

Tools: `classify_crisis`, `save_classification`

---

#### `matching_agent`
Algoritmo híbrido de 3 estágios: (1) filtro geográfico haversine dentro do raio do voluntário, (2) similaridade cosseno entre embeddings Granite 278M da crise e do perfil, (3) bônus por correspondência exata de habilidades (+0.15), histórico (+0.10), idioma (+0.08), proximidade (+0.10) e penalidade por notificação recente (−0.10). Para severity 5, expande o raio 3× e notifica top 10 voluntários.

Tools: `match_volunteers`, `notify_telegram`, `notify_whatsapp`

---

#### `communication_agent`
Gerencia comunicação multicanal: Telegram (principal, 30 msg/s), WhatsApp via Twilio (severity ≥ 4, 1 msg/s), e email para ONGs. Implementa rate limiting, retry automático em 3 tentativas, deduplicação de mensagens e registro auditável de todas as comunicações no banco de dados.

Tools: `notify_telegram`, `notify_whatsapp`

---

#### `optimization_agent`
Analisa distribuição de voluntários em múltiplas crises simultâneas. Detecta redundâncias (>150% da capacidade necessária) e lacunas de cobertura (severity ≥ 3 sem cobertura mínima). Calcula KPIs: taxa de confirmação, tempo médio de resposta, taxa de conclusão e score de impacto. Dispara alerta crítico se `coverage_score < 0.5`.

Tools: `analyze_distribution`, `suggest_reallocation`

---

#### `prediction_agent`
Inteligência preditiva: analisa padrões em eventos recentes e gera previsões de risco para os próximos 7–30 dias. Coleta dados de USGS, GDACS e GDELT, passa a lista consolidada para `predict_humanitarian_risk` (Granite 3.3-8B) e retorna até 10 previsões ordenadas por probabilidade (high → low) com ações preventivas recomendadas.

Tools: `predict_humanitarian_risk`, `fetch_gdacs`, `fetch_usgs`, `fetch_conflict_data`

---

#### `volunteer_agent`
Assistente de matching para voluntários no chat da plataforma web. Responde sempre em português brasileiro. Recebe contexto enriquecido com perfil do voluntário (nome, habilidades, localização, raio) e lista das 10 crises mais próximas. Recomenda apenas crises da lista recebida onde o voluntário pode contribuir com suas habilidades.

---

#### `assistant_agent`
Especialista em planejamento de campanhas humanitárias para ONGs. Responde sempre em português com formato estruturado fixo: Resumo da necessidade → Habilidades necessárias → Número de voluntários recomendado → Urgência → Descrição da campanha. Não usa ferramentas externas — raciocina apenas com o modelo de linguagem.

---

### Ferramentas

As tools são registradas no IBM watsonx Orchestrate via decorator `@tool` e também utilizadas diretamente pelo middleware como fallback.

| Ferramenta | Descrição |
|-----------|-----------|
| `fetch_usgs` | Busca terremotos do USGS (M4.5+) via GeoJSON. Mapeia magnitude para severidade 1–5. Suporta janelas de 1, 7 ou 30 dias. |
| `fetch_gdacs` | Consome o feed RSS/XML do GDACS para enchentes, ciclones, terremotos, vulcões e incêndios. Filtra por nível de alerta (green/orange/red). |
| `fetch_eonet` | Busca eventos NASA EONET (incêndios florestais, tempestades severas, vulcões, secas). Usa a geometria mais recente de cada evento. |
| `fetch_conflict_data` | Baixa o CSV zip do GDELT Events v2 (atualizado a cada 15 min), filtra eventos de conflito armado (CAMEO roots 18/19/20) em zonas ativas, e inclui fallback hardcoded para os maiores conflitos conhecidos. |
| `fetch_reliefweb` | Consome a API REST do ReliefWeb (ONU/OCHA) para desastres humanitários com status `current`. |
| `classify_crisis` | Classifica severidade, urgência e tipo de uma crise usando prompt few-shot com Granite 3.3-8B via watsonx AI SDK. Retorna JSON com confidence e justificativa. |
| `save_classification` | Combina o evento original com a classificação do `classify_crisis` e salva via `POST /save_events` na API do VPS. |
| `match_volunteers` | Encontra os voluntários mais compatíveis usando embeddings Granite 278M (similaridade cosseno) + filtro geográfico haversine + bônus de habilidades. |
| `notify_telegram` | Envia alertas formatados em Markdown via Telegram Bot API para a lista de matches. Registra cada envio no banco antes de enviar. Rate limit: 25 msg/s. |
| `notify_whatsapp` | Envia alertas via WhatsApp usando Twilio. Ativado apenas para severity ≥ 4. Rate limit: 1 msg/s (sandbox). |
| `analyze_distribution` | Analisa o banco de dados e retorna redundâncias, lacunas de cobertura, KPIs e score global de cobertura. |
| `suggest_reallocation` | Recebe o resultado do `analyze_distribution` e gera lista de realocações específicas de voluntários, ordenadas por ganho de impacto estimado. |
| `predict_humanitarian_risk` | Passa lista de eventos recentes para Granite 3.3-8B com prompt de análise prospectiva. Retorna até 10 previsões de risco em JSON com localização, probabilidade e ação preventiva. |

---

### Funcionalidades por Perfil

#### Voluntário
- **Mapa interativo** com todos os eventos de crise ativos, filtráveis por país, severidade e tipo
- **Inscrição em crises** diretamente no mapa com um clique
- **Perfil** com habilidades, localização, raio de atuação e `link_code` para vincular o Telegram
- **Chat com IA** (volunteer_agent): recebe recomendações personalizadas de crises baseadas em perfil e localização
- **Bot Telegram**: alertas automáticos a cada 30 min, inscrição via botão inline, consulta de perfil e crises

#### ONG
- **Mapa interativo** com inscrição em crises que a ONG deseja apoiar
- **Dashboard** com métricas: voluntários selecionados, campanhas ativas, crises apoiadas, distribuição de habilidades
- **Gerenciamento de campanhas**: criar, editar, listar voluntários por campanha, confirmar/recusar candidaturas
- **Chat com IA** (assistant_agent): planejamento estruturado de campanhas humanitárias

#### Admin
- **Mapa completo** sem restrições de perfil
- **Trigger de ingestão manual** de dados via endpoint `/api/ingest`
- Acesso a todas as rotas sem redirecionamento

---

### Schema do Banco de Dados

#### `users`
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INTEGER PK | Identificador único |
| `name` | TEXT | Nome completo |
| `email` | TEXT | Email (login) |
| `password_hash` | TEXT | SHA-256 da senha |
| `role` | TEXT | `volunteer`, `org` ou `admin` |
| `skills` | TEXT | JSON array de habilidades |
| `languages` | TEXT | JSON array de idiomas |
| `lat` | REAL | Latitude |
| `lon` | REAL | Longitude |
| `radius_km` | REAL | Raio de atuação em km |
| `org_name` | TEXT | Nome da organização (ONGs) |
| `available` | INTEGER | 1=disponível, 0=indisponível |
| `link_code` | TEXT UNIQUE | Código para vincular Telegram (ex: `AB12-CD34`) |
| `telegram_id` | INTEGER | ID do chat Telegram vinculado |
| `username` | TEXT | Username Telegram |
| `phone` | TEXT | Número de telefone (WhatsApp) |

#### `crises`
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | TEXT PK | Identificador único (ex: `usgs-us2000abc`) |
| `title` | TEXT | Título descritivo do evento |
| `country` | TEXT | Nome do país |
| `country_iso3` | TEXT | Código ISO3 do país |
| `lat` | REAL | Latitude do epicentro |
| `lon` | REAL | Longitude do epicentro |
| `severity` | REAL | Severidade 1–5 |
| `urgency` | TEXT | `immediate`, `24h`, `48h`, `7days`, `monitoring` |
| `crisis_type` | TEXT | `seismic`, `meteorological`, `humanitarian`, `conflict`, `wildfire`, `drought`, `sanitary` |
| `source` | TEXT | Fonte: `usgs`, `gdacs`, `eonet`, `gdelt`, `reliefweb`, `fallback` |
| `people_affected` | INTEGER | Estimativa de pessoas afetadas |
| `created_at` | TEXT | Timestamp de criação (UTC) |
| `updated_at` | TEXT | Timestamp de atualização (UTC) |

#### `missions`
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INTEGER PK | Identificador único |
| `crisis_id` | TEXT | ID da crise associada |
| `telegram_id` | INTEGER | ID Telegram do criador (bot) |
| `user_id` | INTEGER | ID do usuário na plataforma |
| `username` | TEXT | Username Telegram |
| `status` | TEXT | Status da missão (`active`, `Concluida`, etc.) |
| `created_at` | TEXT | Timestamp de criação (UTC) |

#### `matches`
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INTEGER PK | Identificador único |
| `crisis_id` | TEXT | ID da crise |
| `volunteer_id` | INTEGER | ID do voluntário |
| `score` | REAL | Score de compatibilidade 0–1 |
| `status` | TEXT | `pending`, `notified`, `notified_whatsapp`, `confirmed` |
| `notified_at` | TEXT | Timestamp da notificação (UTC) |

#### `crisis_associations`
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INTEGER PK | Identificador único |
| `crisis_id` | TEXT NOT NULL | ID da crise |
| `user_id` | INTEGER NOT NULL | ID do usuário |
| `role` | TEXT | `volunteer` ou `org` |
| `created_at` | TEXT | Timestamp de criação (UTC) |

#### `campaigns`
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INTEGER PK | Identificador único |
| `org_id` | INTEGER NOT NULL | ID da ONG criadora |
| `title` | TEXT | Título da campanha |
| `description` | TEXT | Descrição detalhada |
| `crisis_id` | TEXT | ID da crise associada |
| `skills_needed` | TEXT | JSON array de habilidades necessárias |
| `target_volunteers` | INTEGER | Número alvo de voluntários |
| `start_date` | TEXT | Data de início |
| `end_date` | TEXT | Data de término |
| `urgency` | TEXT | `baixa`, `media`, `alta`, `critica` |
| `status` | TEXT | `active`, `pending`, `closed` |
| `created_at` | TEXT | Timestamp de criação (UTC) |

#### `campaign_volunteers`
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INTEGER PK | Identificador único |
| `campaign_id` | INTEGER | Referência a `campaigns.id` |
| `volunteer_id` | INTEGER | Referência a `users.id` |
| `status` | TEXT | `selected`, `confirmed`, `declined`, `removed` |
| `added_at` | TIMESTAMP | Timestamp de adição |

#### `telegram_subscribers`
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INTEGER PK | Identificador único |
| `telegram_id` | INTEGER NOT NULL | ID do chat Telegram |
| `username` | TEXT | Username Telegram |
| `country` | TEXT NOT NULL | País de interesse para alertas |
| `created_at` | DATETIME | Timestamp de inscrição |

---

### Referência da API

Base URL: `http://localhost:8000` (dev) | `http://middleware:8000` (Docker)

#### Sistema
| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/` | Status da API |
| `GET` | `/stats` | Contadores: crises, voluntários, missões, matches, alta severidade |
| `GET` | `/ingest/status` | Último ingest: timestamp, contagem e se está desatualizado |
| `POST` | `/ingest` | Dispara ingestão completa (Orchestrate + fallback direto) |

#### Crises
| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/events` | Lista crises com filtros: `country`, `min_severity`, `crisis_type`, `limit`, `order_by` |
| `POST` | `/save_event` | Salva um único evento de crise |
| `POST` | `/save_events` | Salva lista de eventos em lote |
| `GET` | `/events/{crisis_id}/associations` | Contagem de voluntários e ONGs associados a uma crise |
| `POST` | `/events/{crisis_id}/associate` | Associa usuário a uma crise (voluntário ou ONG) |
| `DELETE` | `/events/{crisis_id}/associate/{user_id}` | Remove associação de usuário com crise |
| `GET` | `/predictions` | Previsões de risco humanitário (cache de 1 hora) |

#### Usuários
| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/users/{user_id}` | Dados do usuário (sem password_hash) |
| `PUT` | `/users/{user_id}` | Atualiza disponibilidade ou habilidades |
| `GET` | `/user/by-code/{code}` | Busca voluntário pelo link_code (ignora hífens, role=volunteer) |
| `POST` | `/user/{user_id}/telegram` | Vincula telegram_id e username ao usuário |
| `POST` | `/user/{user_id}/associate-crisis` | Inscreve usuário em uma crise |
| `GET` | `/user/{user_id}/crises` | Lista crises em que o usuário está inscrito |
| `GET` | `/users/with-telegram` | Lista usuários com Telegram vinculado |

#### Voluntários
| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/volunteers` | Cria voluntário (via bot/API) |
| `GET` | `/volunteers` | Lista voluntários disponíveis por habilidade |
| `GET` | `/volunteers/available` | Lista voluntários disponíveis com filtro por crise e raio |
| `PUT` | `/volunteer/radius` | Atualiza raio de atuação do voluntário |
| `GET` | `/users/{user_id}/missions` | Lista crises associadas do usuário |

#### Missões
| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/missions` | Cria missão manual (via bot) |
| `GET` | `/missions` | Lista missões com filtros: `telegram_id`, `user_id`, `status`, `org_id` |

#### Campanhas
| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/campaigns` | Cria campanha de ONG |
| `GET` | `/campaigns` | Lista campanhas com filtro por `org_id` |
| `GET` | `/campaigns/{id}` | Detalhes da campanha com voluntários associados |
| `PUT` | `/campaigns/{id}` | Atualiza campanha |
| `GET` | `/campaigns/{id}/growth` | Crescimento de voluntários por dia (últimos 7 dias) |
| `GET` | `/campaigns/{id}/volunteers` | Lista voluntários da campanha |
| `POST` | `/campaigns/{id}/volunteers` | Adiciona voluntário à campanha |
| `DELETE` | `/campaigns/{id}/volunteers/{volunteer_id}` | Remove voluntário da campanha |
| `PUT` | `/campaign_volunteers/{cv_id}` | Atualiza status do voluntário (`confirmed`/`declined`/`removed`) |
| `GET` | `/volunteer/{user_id}/campaigns` | Campanhas em que o voluntário foi convidado |
| `GET` | `/volunteer/{user_id}/campaigns/pending` | Contagem de convites pendentes |

#### Chat & Notificações
| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/chat` | Envia mensagem para agente de IA (volunteer_agent ou assistant_agent) |
| `POST` | `/subscribe` | Inscreve usuário Telegram para alertas por país |
| `GET` | `/subscribers` | Lista inscritos de um país |

---

### Instalação

#### Pré-requisitos
- Docker Desktop 24+ e Docker Compose v2
- Python 3.12 (para desenvolvimento local)
- Conta IBM Cloud com watsonx Orchestrate e watsonx AI (região `br-sao`)
- Bot Telegram criado via [@BotFather](https://t.me/BotFather)
- (Opcional) Conta Stadia Maps para tiles de mapa, conta Twilio para WhatsApp

#### 1. Clonar e configurar variáveis de ambiente

```bash
git clone https://github.com/Albuqr/Hackathon-IBM.git
cd Hackathon-IBM
cp .env.example .env   # editar com seus valores
```

Edite o `.env` com suas credenciais (veja a tabela de [Variáveis de Ambiente](#variáveis-de-ambiente)).

#### 2. Inicializar o banco de dados

O banco é criado automaticamente pelo middleware na primeira execução. Para pré-popular:

```bash
mkdir -p data
# O schema é criado automaticamente pelo FastAPI no startup
```

#### 3. Rodar com Docker Compose

```bash
docker compose up --build -d
```

Serviços disponíveis:
- Frontend: `http://localhost:5000`
- Middleware: `http://localhost:8001`
- Bot Telegram: ativo em background (long-polling)

#### 4. Rodar localmente (sem Docker)

```bash
# Middleware
pip install -r middleware/requirements.txt
uvicorn middleware.main:app --reload --port 8000

# Frontend (outro terminal)
pip install -r frontend/requirements.txt
python frontend/app.py

# Bot (outro terminal)
pip install -r telegram_bot/requirements.txt
python telegram_bot/bot.py
```

#### 5. Deploy em produção com Easypanel

O projeto está configurado para deploy no [Easypanel](https://easypanel.io) com Traefik e Let's Encrypt. O `docker-compose.yml` inclui labels para roteamento automático em `hackathon.albuqr.com`. Certifique-se de que a rede `easypanel-hktn2k26` existe no seu servidor antes de subir.

---

### Bot Telegram

#### Comandos

| Comando | Descrição |
|---------|-----------|
| `/start` | Mensagem de boas-vindas. Se a conta já estiver vinculada, exibe nome do usuário. |
| `/vincular <CÓDIGO>` | Vincula a conta da plataforma ao Telegram usando o `link_code` do perfil. Ex: `/vincular AB12-CD34` |
| `/crises` | Lista as 5 crises ativas mais graves (severity ≥ 3) com botões inline para inscrição. |
| `/meusdados` | Exibe perfil do voluntário: nome, função, habilidades, localização e raio de atuação. |
| `/inscrever <ID>` | Inscreve o voluntário em uma crise pelo ID. Ex: `/inscrever usgs-us2000abc` |

#### Fluxo de vinculação

1. O voluntário acessa seu perfil na plataforma web e copia o `link_code` (formato `XXXX-XXXX`)
2. Envia `/vincular XXXX-XXXX` no bot
3. O bot consulta o middleware em `GET /user/by-code/{code}` (insensível a hífens, role=volunteer)
4. Após validação, o `telegram_id` é salvo via `POST /user/{id}/telegram`
5. O perfil fica disponível para alertas automáticos e chat com IA

#### Alertas automáticos

O bot executa `alert_job` a cada **30 minutos** (primeiro disparo após 60 segundos):
1. Busca eventos com severity ≥ 4 (últimos 100)
2. Busca todos os usuários com Telegram vinculado
3. Para cada evento × usuário, calcula distância haversine
4. Se a crise estiver dentro do raio de atuação do voluntário, envia alerta formatado em Markdown com botão de inscrição

#### Mensagens de texto livre

Ao enviar qualquer mensagem de texto, o bot:
1. Injeta contexto completo: perfil do voluntário + as 10 crises mais próximas com distâncias
2. Envia para o `volunteer_agent` via `POST /chat`
3. Retorna a resposta em português com botões inline para inscrição nas crises recomendadas

---

### Fontes de Dados Externas

| Fonte | Tipo de Dado | Atualização | Cobertura |
|-------|-------------|-------------|-----------|
| **USGS** | Terremotos M4.5+ | Contínua | Global |
| **GDACS** | Enchentes, ciclones, terremotos, vulcões, secas, incêndios | Contínua | Global |
| **NASA EONET** | Incêndios florestais, tempestades severas, vulcões, secas | Contínua | Global |
| **GDELT Events v2** | Conflitos armados, violência (CAMEO roots 18/19/20) | A cada 15 min | Global (zonas ativas) |
| **ReliefWeb (ONU/OCHA)** | Desastres humanitários com status `current` | Diária | Global |
| **Fallback hardcoded** | Gaza, Ucrânia, Sudão, Myanmar, Iêmen, Congo, Haiti, Líbano, Irã | Permanente | Conflitos ativos conhecidos |

---

### Variáveis de Ambiente

| Variável | Descrição (PT) | Descrição (EN) | Exemplo |
|----------|---------------|---------------|---------|
| `WO_API_KEY` | Chave de API do IBM watsonx Orchestrate | IBM watsonx Orchestrate API key | `your-api-key` |
| `WO_INSTANCE` | URL da instância do watsonx Orchestrate | watsonx Orchestrate instance URL | `https://api.br-sao.watson-orchestrate.cloud.ibm.com/instances/...` |
| `ORCHESTRATOR_AGENT_ID` | ID do agente `crisis_orchestrator` no Orchestrate | crisis_orchestrator agent ID | `uuid-v4` |
| `MONITORING_AGENT_ID` | ID do agente `monitoring_agent` | monitoring_agent ID | `uuid-v4` |
| `CLASSIFICATION_AGENT_ID` | ID do agente `classification_agent` | classification_agent ID | `uuid-v4` |
| `MATCHING_AGENT_ID` | ID do agente `matching_agent` | matching_agent ID | `uuid-v4` |
| `OPTIMIZATION_AGENT_ID` | ID do agente `optimization_agent` | optimization_agent ID | `uuid-v4` |
| `COMMUNICATION_AGENT_ID` | ID do agente `communication_agent` | communication_agent ID | `uuid-v4` |
| `PREDICTION_AGENT_ID` | ID do agente `prediction_agent` | prediction_agent ID | `uuid-v4` |
| `VOLUNTEER_AGENT_ID` | ID do agente `volunteer_agent` | volunteer_agent ID | `uuid-v4` |
| `ASSISTANT_AGENT_ID` | ID do agente `assistant_agent` | assistant_agent ID | `uuid-v4` |
| `WATSONX_APIKEY` | Chave de API do IBM watsonx AI (para Granite) | IBM watsonx AI API key | `your-api-key` |
| `WATSONX_PROJECT_ID` | ID do projeto no watsonx AI | watsonx AI project ID | `uuid-v4` |
| `TG_TOKEN` | Token do bot Telegram (obtido no BotFather) | Telegram Bot token | `1234567890:ABC...` |
| `SECRET_KEY` | Chave secreta para sessões Flask | Flask session secret key | `random-hex-string` |
| `DB_PATH` | Caminho para o arquivo SQLite | SQLite database path | `data/crisis.db` |
| `DATABASE_URL` | URL do banco (referência, SQLite) | Database URL | `sqlite:///data/crisis.db` |
| `STADIA_API_KEY` | Chave para tiles Stadia Maps | Stadia Maps tile API key | `your-stadia-key` |
| `VPS_API_URL` | URL base da API de produção (VPS) | Production VPS API base URL | `http://your-server:port` |
| `TWILIO_ACCOUNT_SID` | Account SID do Twilio (WhatsApp) | Twilio Account SID | `ACxxxxxxxx` |
| `TWILIO_AUTH_TOKEN` | Auth token do Twilio | Twilio Auth Token | `your-auth-token` |
| `TWILIO_WHATSAPP_NUMBER` | Número WhatsApp Twilio (sem `whatsapp:`) | Twilio WhatsApp number | `+14155238886` |

---

### Licença

MIT License © 2025 HKTN26 Team

---
---

## English

### Table of Contents

1. [Overview](#overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Tech Stack](#tech-stack)
4. [AI Agents](#ai-agents)
5. [Tools](#tools)
6. [Features by Role](#features-by-role)
7. [Database Schema](#database-schema)
8. [API Reference](#api-reference)
9. [Setup](#setup)
10. [Telegram Bot](#telegram-bot)
11. [External Data Sources](#external-data-sources)
12. [Environment Variables](#environment-variables)
13. [License](#license-1)

---

### Overview

**Crisis Monitor** is a humanitarian intelligence platform built for the **UNASP + IBM Hackathon HKTN26**. The system addresses a critical gap in disaster response: **decentralized coordination between volunteers, NGOs, and real-time crisis data**.

When a crisis erupts — an earthquake, armed conflict, flood, or disease outbreak — humanitarian response often fails not from a lack of volunteers, but from a lack of coordination. Willing volunteers don't know where they're needed most. NGOs can't mobilize the right skills to the right place. Data from multiple international sources remains scattered and unprocessed.

Crisis Monitor solves this with:

- **Automatic ingestion** of data from 5 international sources (USGS, GDACS, NASA EONET, GDELT, ReliefWeb) in real time
- **AI pipeline** using IBM watsonx Orchestrate and IBM Granite 3.3-8B to classify, prioritize, and match crises to volunteers
- **Web platform** with interactive maps and role-differentiated dashboards (Volunteer, NGO, Admin)
- **Telegram Bot** for automatic alerts and mission enrollment directly from mobile
- **Predictive forecasting** of future humanitarian risks with a 7–30 day horizon

---

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL USERS                                │
│   Web Browser            Telegram Bot          External APIs            │
└──────────┬───────────────────┬───────────────────────┬──────────────────┘
           │                   │                       │
           ▼                   ▼                       │
┌──────────────────┐  ┌────────────────────┐          │
│  Landing Page    │  │   Telegram Bot     │          │
│  (React/Vite)    │  │   python-telegram- │          │
│  Flask-served    │  │   bot + job-queue  │          │
└────────┬─────────┘  └────────┬───────────┘          │
         │                     │                      │
         ▼                     ▼                      │
┌────────────────────────────────────────┐            │
│      Flask Frontend (port 5000)        │            │
│  - Jinja2 templates (map, dashboard)   │            │
│  - Auth (session, SHA-256 hash)        │            │
│  - Role-based routing                  │            │
│  - API proxy to middleware             │            │
└────────────────┬───────────────────────┘            │
                 │                                    │
                 ▼                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│              FastAPI Middleware (port 8000)                            │
│  - Full REST API (40+ endpoints)                                       │
│  - Data ingestion + AI pipeline via watsonx Orchestrate                │
│  - Predictive forecasting with Granite                                 │
│  - SQLite database                                                     │
│  - Startup: auto-backfill missing link_codes                           │
└────────┬──────────────────────────────────────────┬────────────────────┘
         │                                          │
         ▼                                          ▼
┌───────────────────────┐              ┌────────────────────────────────┐
│  SQLite (crisis.db)   │              │  IBM watsonx Orchestrate       │
│  - users              │              │  (br-sao region)               │
│  - crises             │              │                                │
│  - missions           │              │  ┌──────────────────────────┐  │
│  - matches            │              │  │  crisis_orchestrator     │  │
│  - crisis_associations│              │  │  ├── monitoring_agent    │  │
│  - campaigns          │              │  │  └── classification_agent│  │
│  - campaign_volunteers│              │  ├── matching_agent         │  │
│  - telegram_subscribers              │  ├── communication_agent    │  │
└───────────────────────┘              │  ├── optimization_agent     │  │
                                       │  ├── prediction_agent       │  │
                                       │  ├── volunteer_agent        │  │
                                       │  └── assistant_agent        │  │
                                       │                              │  │
                                       │  IBM Granite 3.3-8B Instruct│  │
                                       │  IBM Granite Embedding 278M │  │
                                       └──────────────────────────────┘  │
                                                                         │
┌────────────────────────────────────────────────────────────────────────┘
│   EXTERNAL DATA SOURCES (consumed by tools / middleware)
│   ├── USGS      — real-time earthquakes (GeoJSON)
│   ├── GDACS     — global natural disasters (RSS/XML)
│   ├── NASA EONET— wildfires, storms, volcanoes (JSON)
│   ├── GDELT v2  — armed conflicts (CSV zip, every 15 min)
│   └── ReliefWeb — UN/OCHA humanitarian disasters (REST API)
└────────────────────────────────────────────────────────────────────────
```

---

### Tech Stack

| Layer | Technology | Details |
|-------|-----------|---------|
| **Frontend** | Flask 3.x + Jinja2 | Python server rendering HTML/CSS/JS |
| **Landing Page** | React + Vite (pre-built) | Static bundle served by Flask |
| **Maps** | Leaflet.js + Stadia Maps | Satellite/street tiles with crisis markers |
| **Middleware** | FastAPI + Uvicorn | Async REST API, Python 3.12 |
| **Database** | SQLite 3 | Single file `data/crisis.db`, shared via Docker volume |
| **AI — Orchestration** | IBM watsonx Orchestrate 2.8.0 | Multi-agent pipeline, `br-sao` region |
| **AI — Models** | IBM Granite 3.3-8B Instruct | Classification, chat, prediction |
| **AI — Embeddings** | IBM Granite Embedding 278M Multilingual | Semantic volunteer matching |
| **Bot** | python-telegram-bot 20.x + job-queue | Long-polling, automatic alerts every 30 min |
| **Notifications** | Telegram Bot API + Twilio (WhatsApp) | Twilio enabled only for severity ≥ 4 |
| **Containerization** | Docker + Docker Compose | 3 services: `middleware`, `frontend`, `bot` |
| **Deployment** | Easypanel + Traefik | Automatic HTTPS via Let's Encrypt |

---

### AI Agents

All agents are of type `native`, use the model `watsonx/ibm/granite-3-8b-instruct` with ReAct/default style, and are registered in IBM watsonx Orchestrate.

#### `crisis_orchestrator`
Supervisor agent for the data ingestion pipeline. Coordinates the full cycle: delegates data collection to `monitoring_agent`, collects classifications from `classification_agent` for each event, saves results via the VPS API, and returns a structured JSON report with counts and errors. **Not used for user chat.**

Collaborators: `monitoring_agent`, `classification_agent`

---

#### `monitoring_agent`
Specialist in collection, normalization, and deduplication of global crisis data. Monitors 5 simultaneous sources (ReliefWeb, GDACS, USGS, NASA EONET, GDELT/conflicts). Normalizes heterogeneous events to a unified JSON format with geographic coordinates, type, source, UTC timestamp, and estimated affected population. Deduplicates based on geographic proximity (50 km radius) + same type + 24-hour window.

Tools: `fetch_reliefweb`, `fetch_gdacs`, `fetch_usgs`, `fetch_conflict_data`

---

#### `classification_agent`
Classifies raw events using IBM Granite 3.3-8B with few-shot prompts calibrated in Portuguese and English. Assigns severity 1–5, urgency (immediate/24h/48h/7days/monitoring), and crisis type. Uses the precautionary principle: when in doubt between two levels, chooses the higher one. Saves classifications to the database via `save_classification`.

Tools: `classify_crisis`, `save_classification`

---

#### `matching_agent`
Hybrid 3-stage algorithm: (1) haversine geographic filter within volunteer radius, (2) cosine similarity between Granite 278M embeddings of the crisis and volunteer profile, (3) bonuses for exact skill match (+0.15), history (+0.10), language (+0.08), proximity (+0.10) and penalty for recent notification (−0.10). For severity 5, expands radius 3× and notifies top 10 volunteers.

Tools: `match_volunteers`, `notify_telegram`, `notify_whatsapp`

---

#### `communication_agent`
Manages multi-channel communication: Telegram (primary, 30 msg/s), WhatsApp via Twilio (severity ≥ 4, 1 msg/s), and email for NGOs. Implements rate limiting, automatic 3-attempt retry, message deduplication, and a full auditable log of all communications in the database.

Tools: `notify_telegram`, `notify_whatsapp`

---

#### `optimization_agent`
Analyzes volunteer distribution across multiple simultaneous crises. Detects redundancies (>150% of needed capacity) and coverage gaps (severity ≥ 3 without minimum coverage). Calculates KPIs: confirmation rate, average response time, completion rate, and impact score. Triggers critical alert if `coverage_score < 0.5`.

Tools: `analyze_distribution`, `suggest_reallocation`

---

#### `prediction_agent`
Predictive intelligence: analyzes patterns in recent events and generates risk forecasts for the next 7–30 days. Collects data from USGS, GDACS, and GDELT, passes the consolidated list to `predict_humanitarian_risk` (Granite 3.3-8B), and returns up to 10 predictions ordered by probability (high → low) with recommended preventive actions.

Tools: `predict_humanitarian_risk`, `fetch_gdacs`, `fetch_usgs`, `fetch_conflict_data`

---

#### `volunteer_agent`
Matching assistant for volunteers in the web platform chat. Always responds in Brazilian Portuguese. Receives enriched context with the volunteer's profile (name, skills, location, radius) and a list of the 10 nearest crises. Recommends only crises from the received list where the volunteer can contribute with their skills.

---

#### `assistant_agent`
Humanitarian campaign planning specialist for NGOs. Always responds in Portuguese with a fixed structured format: Summary → Required skills → Recommended number of volunteers → Urgency → Campaign description. Uses no external tools — relies solely on the language model.

---

### Tools

Tools are registered in IBM watsonx Orchestrate via the `@tool` decorator and also used directly by the middleware as a fallback.

| Tool | Description |
|------|-------------|
| `fetch_usgs` | Fetches USGS earthquakes (M4.5+) via GeoJSON. Maps magnitude to severity 1–5. Supports 1, 7, or 30-day windows. |
| `fetch_gdacs` | Consumes the GDACS RSS/XML feed for floods, cyclones, earthquakes, volcanoes, and wildfires. Filters by alert level (green/orange/red). |
| `fetch_eonet` | Fetches NASA EONET events (wildfires, severe storms, volcanoes, droughts). Uses the most recent geometry point of each event. |
| `fetch_conflict_data` | Downloads the GDELT Events v2 CSV zip (updated every 15 min), filters armed conflict events (CAMEO roots 18/19/20) in active zones, and includes hardcoded fallback for major known conflicts. |
| `fetch_reliefweb` | Consumes the ReliefWeb REST API (UN/OCHA) for humanitarian disasters with status `current`. |
| `classify_crisis` | Classifies severity, urgency, and type of a crisis using a few-shot prompt with Granite 3.3-8B via the watsonx AI SDK. Returns JSON with confidence score and justification. |
| `save_classification` | Combines the original event with the classification from `classify_crisis` and saves via `POST /save_events` to the VPS API. |
| `match_volunteers` | Finds the most compatible volunteers using Granite 278M embeddings (cosine similarity) + haversine geographic filter + skill bonuses. |
| `notify_telegram` | Sends Markdown-formatted alerts via the Telegram Bot API to the match list. Logs each send to the database before sending. Rate limit: 25 msg/s. |
| `notify_whatsapp` | Sends alerts via WhatsApp using Twilio. Enabled only for severity ≥ 4. Rate limit: 1 msg/s (sandbox). |
| `analyze_distribution` | Queries the database and returns redundancies, coverage gaps, KPIs, and overall coverage score. |
| `suggest_reallocation` | Receives the `analyze_distribution` result and generates a list of specific volunteer reallocation recommendations, sorted by estimated impact gain. |
| `predict_humanitarian_risk` | Passes a list of recent events to Granite 3.3-8B with a prospective analysis prompt. Returns up to 10 risk predictions in JSON with location, probability, and preventive action. |

---

### Features by Role

#### Volunteer
- **Interactive map** with all active crisis events, filterable by country, severity, and type
- **Crisis enrollment** directly on the map with one click
- **Profile** with skills, location, action radius, and `link_code` for linking Telegram
- **AI Chat** (volunteer_agent): receives personalized crisis recommendations based on profile and location
- **Telegram Bot**: automatic alerts every 30 min, enrollment via inline button, profile and crisis queries

#### NGO
- **Interactive map** with crisis enrollment for crises the NGO wants to support
- **Dashboard** with metrics: selected volunteers, active campaigns, supported crises, skills distribution
- **Campaign management**: create, edit, list volunteers per campaign, confirm/decline applications
- **AI Chat** (assistant_agent): structured humanitarian campaign planning

#### Admin
- **Unrestricted map** without profile redirections
- **Manual data ingestion trigger** via `/api/ingest` endpoint
- Access to all routes without redirection

---

### Database Schema

#### `users`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Unique identifier |
| `name` | TEXT | Full name |
| `email` | TEXT | Email (login) |
| `password_hash` | TEXT | SHA-256 of password |
| `role` | TEXT | `volunteer`, `org`, or `admin` |
| `skills` | TEXT | JSON array of skills |
| `languages` | TEXT | JSON array of languages |
| `lat` | REAL | Latitude |
| `lon` | REAL | Longitude |
| `radius_km` | REAL | Action radius in km |
| `org_name` | TEXT | Organization name (NGOs) |
| `available` | INTEGER | 1=available, 0=unavailable |
| `link_code` | TEXT UNIQUE | Telegram linking code (e.g., `AB12-CD34`) |
| `telegram_id` | INTEGER | Linked Telegram chat ID |
| `username` | TEXT | Telegram username |
| `phone` | TEXT | Phone number (WhatsApp) |

#### `crises`
| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | Unique identifier (e.g., `usgs-us2000abc`) |
| `title` | TEXT | Descriptive event title |
| `country` | TEXT | Country name |
| `country_iso3` | TEXT | ISO3 country code |
| `lat` | REAL | Epicenter latitude |
| `lon` | REAL | Epicenter longitude |
| `severity` | REAL | Severity 1–5 |
| `urgency` | TEXT | `immediate`, `24h`, `48h`, `7days`, `monitoring` |
| `crisis_type` | TEXT | `seismic`, `meteorological`, `humanitarian`, `conflict`, `wildfire`, `drought`, `sanitary` |
| `source` | TEXT | Source: `usgs`, `gdacs`, `eonet`, `gdelt`, `reliefweb`, `fallback` |
| `people_affected` | INTEGER | Estimated number of people affected |
| `created_at` | TEXT | Creation timestamp (UTC) |
| `updated_at` | TEXT | Update timestamp (UTC) |

#### `missions`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Unique identifier |
| `crisis_id` | TEXT | Associated crisis ID |
| `telegram_id` | INTEGER | Telegram ID of the creator (bot) |
| `user_id` | INTEGER | Platform user ID |
| `username` | TEXT | Telegram username |
| `status` | TEXT | Mission status (`active`, `Concluida`, etc.) |
| `created_at` | TEXT | Creation timestamp (UTC) |

#### `matches`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Unique identifier |
| `crisis_id` | TEXT | Crisis ID |
| `volunteer_id` | INTEGER | Volunteer user ID |
| `score` | REAL | Compatibility score 0–1 |
| `status` | TEXT | `pending`, `notified`, `notified_whatsapp`, `confirmed` |
| `notified_at` | TEXT | Notification timestamp (UTC) |

#### `crisis_associations`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Unique identifier |
| `crisis_id` | TEXT NOT NULL | Crisis ID |
| `user_id` | INTEGER NOT NULL | User ID |
| `role` | TEXT | `volunteer` or `org` |
| `created_at` | TEXT | Creation timestamp (UTC) |

#### `campaigns`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Unique identifier |
| `org_id` | INTEGER NOT NULL | Creating NGO's user ID |
| `title` | TEXT | Campaign title |
| `description` | TEXT | Detailed description |
| `crisis_id` | TEXT | Associated crisis ID |
| `skills_needed` | TEXT | JSON array of required skills |
| `target_volunteers` | INTEGER | Target number of volunteers |
| `start_date` | TEXT | Start date |
| `end_date` | TEXT | End date |
| `urgency` | TEXT | `baixa`, `media`, `alta`, `critica` |
| `status` | TEXT | `active`, `pending`, `closed` |
| `created_at` | TEXT | Creation timestamp (UTC) |

#### `campaign_volunteers`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Unique identifier |
| `campaign_id` | INTEGER | Reference to `campaigns.id` |
| `volunteer_id` | INTEGER | Reference to `users.id` |
| `status` | TEXT | `selected`, `confirmed`, `declined`, `removed` |
| `added_at` | TIMESTAMP | Addition timestamp |

#### `telegram_subscribers`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Unique identifier |
| `telegram_id` | INTEGER NOT NULL | Telegram chat ID |
| `username` | TEXT | Telegram username |
| `country` | TEXT NOT NULL | Country of interest for alerts |
| `created_at` | DATETIME | Subscription timestamp |

---

### API Reference

Base URL: `http://localhost:8000` (dev) | `http://middleware:8000` (Docker)

#### System
| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/` | API status |
| `GET` | `/stats` | Counters: crises, volunteers, missions, matches, high severity |
| `GET` | `/ingest/status` | Last ingest: timestamp, count, and staleness flag |
| `POST` | `/ingest` | Trigger full ingestion (Orchestrate + direct fallback) |

#### Crises
| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/events` | List crises with filters: `country`, `min_severity`, `crisis_type`, `limit`, `order_by` |
| `POST` | `/save_event` | Save a single crisis event |
| `POST` | `/save_events` | Save a batch of events |
| `GET` | `/events/{crisis_id}/associations` | Count of volunteers and NGOs associated with a crisis |
| `POST` | `/events/{crisis_id}/associate` | Associate user with a crisis (volunteer or NGO) |
| `DELETE` | `/events/{crisis_id}/associate/{user_id}` | Remove user association with crisis |
| `GET` | `/predictions` | Humanitarian risk predictions (1-hour cache) |

#### Users
| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/users/{user_id}` | User data (without password_hash) |
| `PUT` | `/users/{user_id}` | Update availability or skills |
| `GET` | `/user/by-code/{code}` | Find volunteer by link_code (hyphen-insensitive, role=volunteer) |
| `POST` | `/user/{user_id}/telegram` | Link telegram_id and username to user |
| `POST` | `/user/{user_id}/associate-crisis` | Enroll user in a crisis |
| `GET` | `/user/{user_id}/crises` | List crises the user is enrolled in |
| `GET` | `/users/with-telegram` | List users with Telegram linked |

#### Volunteers
| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/volunteers` | Create volunteer (via bot/API) |
| `GET` | `/volunteers` | List available volunteers by skill |
| `GET` | `/volunteers/available` | List available volunteers filtered by crisis and radius |
| `PUT` | `/volunteer/radius` | Update volunteer action radius |
| `GET` | `/users/{user_id}/missions` | List user's associated crises |

#### Missions
| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/missions` | Create manual mission (via bot) |
| `GET` | `/missions` | List missions with filters: `telegram_id`, `user_id`, `status`, `org_id` |

#### Campaigns
| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/campaigns` | Create NGO campaign |
| `GET` | `/campaigns` | List campaigns filtered by `org_id` |
| `GET` | `/campaigns/{id}` | Campaign details with associated volunteers |
| `PUT` | `/campaigns/{id}` | Update campaign |
| `GET` | `/campaigns/{id}/growth` | Volunteer growth by day (last 7 days) |
| `GET` | `/campaigns/{id}/volunteers` | List campaign volunteers |
| `POST` | `/campaigns/{id}/volunteers` | Add volunteer to campaign |
| `DELETE` | `/campaigns/{id}/volunteers/{volunteer_id}` | Remove volunteer from campaign |
| `PUT` | `/campaign_volunteers/{cv_id}` | Update volunteer status (`confirmed`/`declined`/`removed`) |
| `GET` | `/volunteer/{user_id}/campaigns` | Campaigns the volunteer was invited to |
| `GET` | `/volunteer/{user_id}/campaigns/pending` | Count of pending invitations |

#### Chat & Notifications
| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/chat` | Send message to AI agent (volunteer_agent or assistant_agent) |
| `POST` | `/subscribe` | Subscribe Telegram user to country alerts |
| `GET` | `/subscribers` | List subscribers for a country |

---

### Setup

#### Prerequisites
- Docker Desktop 24+ and Docker Compose v2
- Python 3.12 (for local development)
- IBM Cloud account with watsonx Orchestrate and watsonx AI (`br-sao` region)
- Telegram bot created via [@BotFather](https://t.me/BotFather)
- (Optional) Stadia Maps account for map tiles, Twilio account for WhatsApp

#### 1. Clone and configure environment variables

```bash
git clone https://github.com/Albuqr/Hackathon-IBM.git
cd Hackathon-IBM
cp .env.example .env   # fill in your values
```

Edit `.env` with your credentials (see the [Environment Variables](#environment-variables) table).

#### 2. Initialize the database

The database is created automatically by the middleware on first run. To pre-populate:

```bash
mkdir -p data
# Schema is created automatically by FastAPI on startup
```

#### 3. Run with Docker Compose

```bash
docker compose up --build -d
```

Services available:
- Frontend: `http://localhost:5000`
- Middleware: `http://localhost:8001`
- Telegram Bot: running in background (long-polling)

#### 4. Run locally (without Docker)

```bash
# Middleware
pip install -r middleware/requirements.txt
uvicorn middleware.main:app --reload --port 8000

# Frontend (separate terminal)
pip install -r frontend/requirements.txt
python frontend/app.py

# Bot (separate terminal)
pip install -r telegram_bot/requirements.txt
python telegram_bot/bot.py
```

#### 5. Production deployment with Easypanel

The project is configured for deployment on [Easypanel](https://easypanel.io) with Traefik and Let's Encrypt. The `docker-compose.yml` includes routing labels for automatic HTTPS at `hackathon.albuqr.com`. Ensure the `easypanel-hktn2k26` network exists on your server before deploying.

---

### Telegram Bot

#### Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message. If account is already linked, displays the user's name. |
| `/vincular <CODE>` | Links the platform account to Telegram using the `link_code` from the profile. E.g., `/vincular AB12-CD34` |
| `/crises` | Lists the 5 most severe active crises (severity ≥ 3) with inline enrollment buttons. |
| `/meusdados` | Displays volunteer profile: name, role, skills, location, and action radius. |
| `/inscrever <ID>` | Enrolls the volunteer in a crisis by ID. E.g., `/inscrever usgs-us2000abc` |

#### Linking flow

1. The volunteer accesses their profile on the web platform and copies the `link_code` (format `XXXX-XXXX`)
2. Sends `/vincular XXXX-XXXX` to the bot
3. The bot queries the middleware at `GET /user/by-code/{code}` (hyphen-insensitive, role=volunteer)
4. After validation, the `telegram_id` is saved via `POST /user/{id}/telegram`
5. The profile becomes available for automatic alerts and AI chat

#### Automatic alerts

The bot runs `alert_job` every **30 minutes** (first run after 60 seconds):
1. Fetches events with severity ≥ 4 (latest 100)
2. Fetches all users with Telegram linked
3. For each event × user, calculates haversine distance
4. If the crisis is within the volunteer's action radius, sends a Markdown-formatted alert with an enrollment button

#### Free text messages

When any text message is sent, the bot:
1. Injects full context: volunteer profile + the 10 nearest crises with distances
2. Sends to `volunteer_agent` via `POST /chat`
3. Returns the response in Portuguese with inline enrollment buttons for the recommended crises

---

### External Data Sources

| Source | Data Type | Update Frequency | Coverage |
|--------|-----------|-----------------|----------|
| **USGS** | Earthquakes M4.5+ | Continuous | Global |
| **GDACS** | Floods, cyclones, earthquakes, volcanoes, droughts, wildfires | Continuous | Global |
| **NASA EONET** | Wildfires, severe storms, volcanoes, droughts | Continuous | Global |
| **GDELT Events v2** | Armed conflicts, violence (CAMEO roots 18/19/20) | Every 15 min | Global (active zones) |
| **ReliefWeb (UN/OCHA)** | Humanitarian disasters with `current` status | Daily | Global |
| **Hardcoded fallback** | Gaza, Ukraine, Sudan, Myanmar, Yemen, DRC, Haiti, Lebanon, Iran | Permanent | Known active conflicts |

---

### Environment Variables

| Variable | Description (PT) | Description (EN) | Example |
|----------|-----------------|-----------------|---------|
| `WO_API_KEY` | Chave de API do IBM watsonx Orchestrate | IBM watsonx Orchestrate API key | `your-api-key` |
| `WO_INSTANCE` | URL da instância do watsonx Orchestrate | watsonx Orchestrate instance URL | `https://api.br-sao.watson-orchestrate.cloud.ibm.com/instances/...` |
| `ORCHESTRATOR_AGENT_ID` | ID do agente `crisis_orchestrator` | crisis_orchestrator agent ID | `uuid-v4` |
| `MONITORING_AGENT_ID` | ID do agente `monitoring_agent` | monitoring_agent ID | `uuid-v4` |
| `CLASSIFICATION_AGENT_ID` | ID do agente `classification_agent` | classification_agent ID | `uuid-v4` |
| `MATCHING_AGENT_ID` | ID do agente `matching_agent` | matching_agent ID | `uuid-v4` |
| `OPTIMIZATION_AGENT_ID` | ID do agente `optimization_agent` | optimization_agent ID | `uuid-v4` |
| `COMMUNICATION_AGENT_ID` | ID do agente `communication_agent` | communication_agent ID | `uuid-v4` |
| `PREDICTION_AGENT_ID` | ID do agente `prediction_agent` | prediction_agent ID | `uuid-v4` |
| `VOLUNTEER_AGENT_ID` | ID do agente `volunteer_agent` | volunteer_agent ID | `uuid-v4` |
| `ASSISTANT_AGENT_ID` | ID do agente `assistant_agent` | assistant_agent ID | `uuid-v4` |
| `WATSONX_APIKEY` | Chave de API do IBM watsonx AI (para Granite) | IBM watsonx AI API key | `your-api-key` |
| `WATSONX_PROJECT_ID` | ID do projeto no watsonx AI | watsonx AI project ID | `uuid-v4` |
| `TG_TOKEN` | Token do bot Telegram (BotFather) | Telegram Bot token | `1234567890:ABC...` |
| `SECRET_KEY` | Chave secreta para sessões Flask | Flask session secret key | `random-hex-string` |
| `DB_PATH` | Caminho para o arquivo SQLite | SQLite database path | `data/crisis.db` |
| `DATABASE_URL` | URL do banco (referência, SQLite) | Database URL | `sqlite:///data/crisis.db` |
| `STADIA_API_KEY` | Chave para tiles Stadia Maps | Stadia Maps tile API key | `your-stadia-key` |
| `VPS_API_URL` | URL base da API de produção (VPS) | Production VPS API base URL | `http://your-server:port` |
| `TWILIO_ACCOUNT_SID` | Account SID do Twilio (WhatsApp) | Twilio Account SID | `ACxxxxxxxx` |
| `TWILIO_AUTH_TOKEN` | Auth token do Twilio | Twilio Auth Token | `your-auth-token` |
| `TWILIO_WHATSAPP_NUMBER` | Número WhatsApp Twilio | Twilio WhatsApp number | `+14155238886` |

---

### License

MIT License © 2025 HKTN26 Team
