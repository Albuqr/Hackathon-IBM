# Gestão de Abrigos, fatia 1: roteiro

Para explicar do começo ao fim o que entrou na branch `feat/brasil-abrigos`. Decisões técnicas:
[ADR 0005](../../docs/adr/0005-papeis-de-gestor-e-abrigo-nao-verificado.md) (papel e abrigo não verificado),
[ADR 0006](../../docs/adr/0006-dados-de-abrigados-e-escopo-da-busca.md) (abrigados e escopo da busca),
[ADR 0008](../../docs/adr/0008-privacidade-da-busca-entre-abrigos.md) (privacidade da busca entre abrigos, emenda a 0006),
[ADR 0007](../../docs/adr/0007-lista-compartilhada-de-itens-e-agente-de-duplicados.md) (lista de itens e duplicados).

> **Antes de usar dados reais (bloqueio):** o tempo de guarda dos dados de quem saiu do abrigo é decisão do cliente
> (LGPD) e não está implementado. Até essa decisão e a implementação, só dados fictícios da semente; nenhum dado real.
> Pendências da fatia: [BACKLOG.md](BACKLOG.md).

## O que foi construído
- Papel novo `gestor_abrigo`, com cadastro aberto (`/brasil/cadastro`) e dois logins de teste (`gestor`, `gestor2`).
- Abrigos do gestor (um gestor pode ter vários): nome, endereço livre, local por GPS ou lat/lon (município IBGE pela
  malha; fora do Brasil = 422), capacidade, permanente/temporário, ativo, sensível, crises vinculadas. Funciona na hora,
  marcado "Não verificado". Verificação de verdade ainda não existe; há uma verificação só de teste.
- Pessoas abrigadas: chegada em etapas (uma pessoa ou um grupo; 2+ viram família), nome e nome da mãe obrigatórios,
  CPF opcional (só 11 dígitos), necessidades especiais, saída, lotação (presentes x capacidade) e busca por nome.
- Estoque e necessidades: lista de itens compartilhada que cresce, status Urgente/Precisa/OK/Sobrando com quantidade
  aproximada, profissionais e veículos só como pedido, e um agente que só sinaliza prováveis duplicados.
- Semente com abrigos, pessoas e estoque fictícios dos dois gestores de teste.

## Rodar local
```bash
export BRASIL_DEV_LOGIN=1 BRASIL_DB_PATH=data/brasil-e2e.db
python -m middleware.brasil.semear_teste          # crises, ONG/voluntários e os abrigos de gestor e gestor2
uvicorn middleware.main:app --port 8000 &
API_URL=http://localhost:8000 python frontend/app.py
```
- A semente recusa rodar sem `BRASIL_DB_PATH` e sem `BRASIL_DEV_LOGIN=1`. Pode rodar quantas vezes quiser: apaga e
  recria os abrigos de `gestor` e `gestor2` (todos os abrigos desses dois). Imprime só contagens, nunca nomes.
- Banco semeado antes da busca ignorar pontuação e das datas em UTC: rode a semente de novo para regravar `nome_busca` e as datas.
- Em http://localhost:5000/brasil/entrar, "Gestor de Abrigo" e "Gestor de Abrigo 2" entram direto em `/brasil/abrigo`.
  - `gestor`: Ginásio da Escola Estadual Fictícia (Porto Alegre, permanente, 60 vagas, crise `teste-poa-4`), com uma
    família de três (gestante e criança sem CPF), uma idosa com problema de saúde, uma pessoa com deficiência e uma
    que já saiu (5 presentes). Estoque: Água Urgente, Colchões Sobrando, Equipe de saúde Precisa 2, Cesta básica OK.
  - `gestor2`: Ginásio Municipal de Teste (Canoas, temporário) com uma família de dois e um idoso, e a Casa de
    Acolhimento de Teste (sensível, uma pessoa). Estoque: Cobertores Urgente, Ambulância Precisa 1, entre outros.
  - Todos começam "Não verificado". Para ver a busca mudar: em `gestor`, Pessoas > buscar "exemplo" (só os dele); no
    painel, "Marcar como verificado" (só de teste); buscar de novo (aparece também a família de Canoas, só com o nome e "Entre em contato com a coordenação
    regional."; a Casa de Acolhimento, sensível, nunca aparece para `gestor`). Cada busca entre abrigos fica em
    `buscas_abrigados_log`.
- Cadastro: http://localhost:5000/brasil/cadastro cria uma conta `gestor_abrigo` e cai na criação do abrigo em etapas.

## Telas
Todo `acao(...)` do navegador vai para `POST /brasil/acao/<nome>` e passa pela `POLITICA`
(`frontend/brasil/encaminhador.py`); "servidor" = o Flask chama a API com a identidade da sessão (`como_eu`).

### `/brasil/cadastro` (`frontend/brasil/__init__.py:cadastro`)
| POLITICA | API | Tabelas |
|---|---|---|
| nenhuma (formulário no servidor) | `POST /brasil/cadastro` | escreve `users` (sempre `role='gestor_abrigo'`) |

### `/brasil/abrigo` e `/brasil/abrigo/<id>/editar` (`abrigo`, `abrigo_editar`; `static/abrigo.js`)
| POLITICA | API | Tabelas |
|---|---|---|
| servidor | `GET /brasil/abrigos`, `GET /brasil/abrigos/{id}` | lê `abrigos`, `abrigo_crises`, `crises`, contagem de `abrigados` |
| `municipio_abrigo` | `GET /brasil/abrigos/municipio` | nenhuma (malha IBGE) |
| `crises` | `GET /brasil/crises` | lê `crises` |
| `criar_abrigo`, `editar_abrigo` | `POST /brasil/abrigos`, `PUT /brasil/abrigos/{id}` | escreve `abrigos`, `abrigo_crises` |
| `dev_verificar_abrigo` | `POST /brasil/dev/abrigos/{id}/verificar` | escreve `abrigos.verificado` |

### `/brasil/abrigo/<id>/pessoas` (`abrigo_pessoas`; `static/pessoas.js`)
| POLITICA | API | Tabelas |
|---|---|---|
| servidor | `GET /brasil/abrigos` (abrigo e se a busca vale para todos) | lê `abrigos` |
| `pessoas_abrigo` | `GET /brasil/abrigos/{id}/pessoas` | lê `abrigados` |
| `registrar_chegada` | `POST /brasil/abrigos/{id}/chegadas` | escreve `familias`, `abrigados` |
| `registrar_saida` | `POST /brasil/abrigados/{pid}/saida` | escreve `abrigados.saida_em` |
| `buscar_abrigados` | `POST /brasil/abrigados/busca` (`{"nome": ...}` no corpo, fora da URL e do log de acesso) | lê `abrigados`, `abrigos`; escreve `buscas_abrigados_log` (só no escopo `todos`) |
| `lotacao_abrigo` (na política, a tela usa a lotação que vem junto) | `GET /brasil/abrigos/{id}/lotacao` | lê `abrigados` |

`entrada_em` e `saida_em` ficam sempre em UTC (`2026-11-18T13:00:00+00:00`); data sem fuso é horário de Brasília (UTC-03:00). Entrada mais de 10 minutos no futuro é recusada (422), e saída antes da entrada também (422). Chegada em abrigo inativo é recusada (409) com a mensagem para reativar o abrigo antes, e a tela troca o botão "Registrar chegada" pelo link para reativar (decisão c).

### `/brasil/abrigo/<id>/estoque` (`abrigo_estoque`; `static/estoque.js`)
| POLITICA | API | Tabelas |
|---|---|---|
| servidor (também `estoque_abrigo`, `grupos_itens` na política) | `GET /brasil/abrigos/{id}`, `GET /brasil/abrigos/{id}/estoque`, `GET /brasil/itens/grupos` | lê `abrigos`, `abrigo_itens`, `itens` |
| `sugerir_itens` | `GET /brasil/itens/sugestoes?q=` | lê `itens` (+ agente de duplicados) |
| `criar_item` | `POST /brasil/itens` | escreve `itens` |
| `atualizar_estoque` | `PUT /brasil/abrigos/{id}/estoque/{item}` | escreve `abrigo_itens` |
| `remover_estoque` | `DELETE /brasil/abrigos/{id}/estoque/{item}` | apaga de `abrigo_itens` |

## Onde estão as regras de acesso
| Regra | Onde |
|---|---|
| Papel por ação no navegador; identidade sempre da sessão | `frontend/brasil/encaminhador.py`: `POLITICA`, `encaminhar`; telas com `exige_login("gestor_abrigo")` em `frontend/brasil/__init__.py` |
| A API confere o papel de novo | `middleware/brasil/acesso.py`: `Acesso.exige` (cada router faz `acesso.exige(PAPEL)`) |
| Só o dono vê o abrigo; outro gestor = 404 | `middleware/brasil/abrigos.py`: `abrigo_do_gestor` (usado por abrigados e estoque) |
| Escopo da busca: todos os abrigos se algum abrigo do gestor estiver verificado, menos os sensíveis de outros gestores; de outros abrigos só nome + contato fixo e só quem não saiu; CPF, datas e abrigo só dos próprios; toda busca entre abrigos registrada, sem rota que leia o registro (ADR 0008) | `abrigos.py`: `gestor_verificado`; `abrigados.py`: `buscar_abrigados`, `SQL_BUSCA`, `CONTATO_OUTRO_ABRIGO`, `SQL_LOG_BUSCA` |
| Profissionais e veículos só como pedido (Urgente/Precisa e quantidade > 0) | `middleware/brasil/estoque.py`: `_so_necessidade`, `atualizar_estoque` |
| Verificação só de teste; 404 sem `BRASIL_DEV_LOGIN=1` | `abrigos.py`: `dev_verificar` |
| Privacidade: listas de abrigo só têm a contagem de presentes; nada imprime/loga pessoas; voluntário/ONG/admin recebem 403 nas rotas de pessoas; abrigados não entram no mapa | `abrigos.py`: `completo`; `abrigados.py` (docstring e rotas); `semear_teste.py`: `abrigos_teste` (resumo só com contagens) |

## Tabelas novas e o merge (ADR 0002)
`abrigos`, `abrigo_crises`, `itens`, `abrigo_itens`, `familias`, `abrigados` (todas só do Brasil, em `db.ESQUEMA`;
`itens` já vem com a lista base). Em `merge_brasil.py` entram em `ORDEM` depois das tabelas de que dependem e em
`REFERENCIAS` (gestor → `users`, abrigo → `abrigos`, item → `itens`, família → `familias`), então os IDs são
renumerados. `abrigo_crises` não tem id próprio: a chave é remapeada. `itens` tem `CHAVE_NATURAL = nome_busca`: se o
Crisis já tem o item com o mesmo nome normalizado, a linha é reaproveitada e o estoque aponta para ela.
`buscas_abrigados_log` (ADR 0008: user_id, consulta, buscado_em, resultados) também entra no merge, com `user_id` → `users`.

## Agente de duplicados
`estoque.possiveis_duplicados` chama `orquestracao.executar(cfg, "itens_duplicados", nome, {"itens": ...})`; o provedor
`local` (`orquestracao/local.py`) responde com a regra `estoque.duplicados` (igual sem acento/plural, um contido no outro,
começo, ou difflib ≥ 0,8). Os outros provedores caem para o local. Só sinaliza ("Possível duplicado de: …"); nunca une
nem renomeia. Mesmo nome normalizado reaproveita o item existente.

## "Pronto quando" x testes
| # | Critério | Testes |
|---|---|---|
| 1 | Cadastro + criar abrigo mostra "Não verificado" | `tests/test_abrigos.py::test_cadastro_cria_so_gestor_de_abrigo_e_email_repetido_409`, `::test_cria_abrigo_nao_verificado_com_municipio_e_uf`; `frontend/brasil/tests/test_frontend.py::test_cadastro_de_gestor_entra_e_vai_para_o_abrigo`, `::test_abrigo_com_abrigos_mostra_o_painel_e_marca_nao_verificado` |
| 2 | Família de três (criança sem CPF), uma saída, lotação | `tests/test_abrigados.py::test_familia_de_tres_vira_uma_familia_e_lotacao_3`, `::test_uma_saida_da_familia_de_tres_deixa_2`, `::test_lista_agrupa_por_familia_e_saida_baixa_a_lotacao` |
| 3 | Escopo da busca antes/depois da verificação de teste | `test_abrigados.py::test_busca_de_gestor_nao_verificado_so_nos_proprios_abrigos`, `::test_busca_depois_de_verificar_acha_nos_dois_e_cpf_so_dos_proprios`; `test_abrigos.py::test_verificacao_de_teste_alterna_e_edicao_nao_muda_verificado`, `::test_verificacao_de_teste_responde_404_sem_login_de_teste`; `test_semente.py::test_semente_pela_api_estoque_lotacao_e_busca_sem_verificar`. ADR 0008: `test_abrigados.py::test_abrigo_sensivel_de_outro_gestor_nunca_aparece_na_busca`, `::test_resultado_de_outro_abrigo_tem_so_nome_e_contato`, `::test_quem_saiu_some_da_busca_de_outros_abrigos_e_continua_para_o_dono`, `::test_visao_do_proprio_gestor_continua_completa`, `::test_toda_busca_entre_abrigos_fica_registrada_mesmo_sem_resultado`, `::test_busca_so_nos_proprios_abrigos_nao_e_registrada`, `::test_registro_de_buscas_nao_sai_por_nenhuma_rota`; `test_semente.py::test_semente_casa_de_acolhimento_e_sensivel_e_fica_fora_da_busca_de_outro_gestor`; `test_merge.py::test_registro_de_buscas_entra_no_merge_com_usuario_remapeado`; `test_frontend.py::test_busca_de_outro_abrigo_mostra_so_nome_e_contato`, `::test_registro_de_buscas_nao_tem_acao_nem_pagina` |
| 4 | Voluntário/ONG (e admin) 403 nas rotas de pessoas, sem vazar dados | `test_abrigados.py::test_outros_perfis_recebem_403_em_toda_rota_de_pessoas`, `::test_dados_de_abrigados_nao_aparecem_para_outros_perfis`, `::test_rotas_de_pessoas_nao_imprimem_dados`, `::test_outro_gestor_recebe_404_nas_pessoas_do_abrigo_alheio`; `test_frontend.py::test_politica_de_abrigados_so_para_gestor_de_abrigo`, `::test_pessoas_do_abrigo_so_para_gestor` |
| 5 | Água Urgente, Colchões Sobrando, item novo sugerido ao segundo gestor, "agua" sinalizado | `tests/test_estoque.py::test_agua_urgente_com_quantidade_e_colchoes_sobrando`, `::test_item_novo_aparece_para_outro_gestor_ao_digitar`, `::test_agua_minuscula_e_sinalizada_como_duplicado_sem_bloquear`, `::test_regra_de_duplicados` |
| 6 | Profissionais e veículos só como pedido | `test_estoque.py::test_profissionais_e_veiculos_so_pedido_com_quantidade`, `::test_grupo_profissionais_forca_so_necessidade_e_veiculo_escolhe`, `::test_lista_base_tem_os_quatro_grupos_e_profissionais_e_veiculos_so_pedido` |
| 7 | Suíte verde (menos o teste de data conhecido) | `pytest`: 430 passam, 1 falha conhecida `test_inteligencia.py::test_fr025_descartada_sai_do_mapa_e_nao_verificada_expira_em_7_dias` (relógio real). Merge: `test_merge.py::test_abrigos_entram_no_merge_...`, `::test_itens_e_estoque_entram_no_merge_...`, `::test_familias_e_abrigados_entram_no_merge_...`; semente: `test_semente.py::test_semente_cria_abrigos_pessoas_e_estoque_ficticios_e_e_idempotente` |
| 8 | Este roteiro | `middleware/brasil/WALKTHROUGH.md` |

Caminhos de teste relativos a `middleware/brasil/` quando não indicado.

## Decisões de produto
Tomadas durante a fatia, sem regra no brief; todas já decididas:
- a) Decidido (ADR 0008): abrigo sensível nunca aparece na busca de outros gestores; só o dono acha a própria gente.
- b) Decidido (ADR 0008): de outros abrigos a busca mostra só o nome e "Entre em contato com a coordenação regional.", e quem saiu não aparece; nos próprios abrigos continua tudo, inclusive quem saiu ("Saiu <data>").
- c) Decidido (João, 2026-11-23): chegada em abrigo inativo é recusada (409), com mensagem clara para reativar o
  abrigo antes; a saída continua valendo. Testes: `test_abrigados.py::test_chegada_em_abrigo_inativo_409_e_nada_e_gravado`,
  `::test_abrigo_criado_inativo_tambem_recusa_chegada`, `::test_saida_de_abrigo_inativo_continua_valendo`,
  `::test_abrigo_inativo_de_outro_gestor_continua_404`; `test_frontend.py::test_pessoas_de_abrigo_inativo_pede_para_reativar_em_vez_de_registrar_chegada`.
- d) Decidido (João, 2026-11-23): saída com data antes da entrada continua recusada (422), já implementado e testado
  (`test_abrigados.py::test_saida_antes_da_entrada_422`).
- e) Decidido (João, 2026-11-23): por quanto tempo guardar os dados de quem saiu é decisão do cliente (LGPD) e não está
  implementado. **Bloqueia carregar dados reais**; até lá só dados fictícios da semente (ver o aviso no topo).
- f) Decidido (João, 2026-11-23): o status Urgente mantém a cor de alerta laranja que já existe (`--acento`), além do
  texto e do "!". Exceção aceita à regra do PRODUCT.md de verde como única cor de destaque.
- g) Decidido (João, 2026-11-23): a curadoria de quase-duplicados da lista compartilhada de itens fica para o backlog;
  hoje o agente só avisa (ADR 0007).
