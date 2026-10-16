# 0003 — Orquestração trocável (local / watsonx / claude) e fontes brasileiras
status: accepted · date: 2026-10-16

## Context
É preciso poder usar outros orquestradores além do watsonx sem mudar o que existe (Q6, FR-028, FR-029), e as fontes globais não cobrem o Brasil (FR-017–FR-020, H1). Sem credenciais neste ambiente, tudo precisa funcionar em fallback (NFR-002, NFR-003).

## Options considered
| Option | Pros | Cons | Fit to NFRs |
|---|---|---|---|
| Interface única `Provedor.executar(agente, mensagem)` com implementações `local`, `watsonx`, `claude`, lendo os `.yaml` atuais dos agentes | mesmos agentes em qualquer provedor; trocar é 1 variável | o provedor `local` é código determinístico, não LLM | NFR-002 (local roda sem rede de IA), FR-028 |
| Framework de agentes externo (ex.: LangGraph) | ecossistema pronto | dependência nova pesada; reescreve os agentes | fere "simplify" (AGENTS.md) |
| Chamar o watsonx direto e só ter fallback fixo | menos código | não permite outro orquestrador | fere Q6 |

Fontes brasileiras: APIs públicas verificadas em 2026-10-16 — INPE (CSV diário de focos com código IBGE), CEMADEN (`wsAlertas2`, JSON com código IBGE), INMET (`avisos/ativos`, JSON com polígono; exige User-Agent). Crises sem API vêm do `brasil_news_agent`, limitado a uma lista fixa de fontes.

## Decision
Camada `middleware/brasil/orquestracao/` com a interface acima; `local` é o padrão; `claude` usa o Messages API com as ferramentas dos `.yaml` como tools; falha ou falta de credencial cai para `local` com log. Fontes BR viram ferramentas novas `tools/br_*.py` no mesmo estilo das atuais; as atuais são importadas sem alteração.

## Consequences
Positivo: provedor novo = uma classe nova. Negativo: no modo `local`, agentes de conversa (chat) respondem por regra, não por LLM — isso é dito na interface.

## Sources
- [Anthropic — Tool use with Claude](https://docs.claude.com/en/docs/agents-and-tools/tool-use/overview) · tier A · 2026-10-16
- [INPE — Programa Queimadas, dados abertos](https://terrabrasilis.dpi.inpe.br/queimadas/portal/) · tier A · 2026-10-16
- [CEMADEN — Painel de alertas](https://painelalertas.cemaden.gov.br/) · tier A · 2026-10-16
- [INMET — Alert-AS (avisos meteorológicos)](https://alertas2.inmet.gov.br/) · tier A · 2026-10-16
