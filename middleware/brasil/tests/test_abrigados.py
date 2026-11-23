"""Pessoas abrigadas (ADR 0006): regras de chegada/saída, lotação, busca e privacidade. Só pessoas fictícias."""
from datetime import datetime, timedelta, timezone

import pytest

from middleware.brasil import db
from middleware.brasil.abrigados import nome_busca

POA = {"lat": -30.0346, "lon": -51.2177}      # Porto Alegre
CANOAS = {"lat": -29.9177, "lon": -51.1836}   # Canoas

FAMILIA = [
    {"nome": "João Fictício da Silva", "nome_mae": "Maria Fictícia da Silva", "cpf": "123.456.789-01"},
    {"nome": "Ana Fictícia da Silva", "nome_mae": "Rosa Fictícia Souza", "cpf": "98765432100", "necessidades": ["gestante"]},
    {"nome": "Pedrinho Fictício da Silva", "nome_mae": "Ana Fictícia da Silva", "necessidades": ["saude", "saude"]},
]
DADOS_PESSOAIS = ("nome_mae", "cpf", "Maria Fictícia", "12345678901", "Pedrinho")


def como(uid) -> dict:
    return {"X-Brasil-Usuario": str(uid)}


def abrigo(cli, uid, capacidade=120, **kw) -> int:
    corpo = {"nome": "Abrigo Ginásio Fictício", "endereco": "", **POA, "capacidade": capacidade, "tipo": "temporario", **kw}
    r = cli.post("/brasil/abrigos", json=corpo, headers=como(uid))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def chegar(cli, uid, aid, pessoas, **kw):
    return cli.post(f"/brasil/abrigos/{aid}/chegadas", json={"pessoas": pessoas, **kw}, headers=como(uid))


@pytest.fixture
def cena(api):
    """gestor (g1) com um abrigo e a família de três; gestor2 (g2) com outro abrigo e uma pessoa."""
    cli, rotas = api
    g1 = cli.post("/brasil/dev/usuario/gestor").json()["id"]
    g2 = cli.post("/brasil/dev/usuario/gestor2").json()["id"]
    a1 = abrigo(cli, g1)
    a2 = abrigo(cli, g2, nome="Escola Fictícia de Canoas", **CANOAS)
    r = chegar(cli, g1, a1, FAMILIA)
    assert r.status_code == 200, r.text
    r2 = chegar(cli, g2, a2, [{"nome": "Joana Fictícia Pereira", "nome_mae": "Clara Fictícia Pereira", "cpf": "11122233344"}])
    assert r2.status_code == 200, r2.text
    return {"cli": cli, "rotas": rotas, "g1": g1, "g2": g2, "a1": a1, "a2": a2, "chegada": r.json(),
            "pessoa_g2": r2.json()["pessoas"][0]["id"]}


# ── regras ───────────────────────────────────────────────────────────
def test_familia_de_tres_vira_uma_familia_e_lotacao_3(cena):
    c = cena["chegada"]
    assert c["familia_id"] is not None and len(c["pessoas"]) == 3
    assert {p["familia_id"] for p in c["pessoas"]} == {c["familia_id"]}
    assert [p["cpf"] for p in c["pessoas"]] == ["12345678901", "98765432100", None]
    assert c["pessoas"][2]["necessidades"] == ["saude"] and all(p["presente"] for p in c["pessoas"])
    assert c["lotacao"] == {"capacidade": 120, "presentes": 3, "livres": 117, "lotado": False, "acima": 0}
    assert c["avisos"] == []
    cli = cena["cli"]
    assert cli.get(f"/brasil/abrigos/{cena['a1']}/lotacao", headers=como(cena["g1"])).json()["presentes"] == 3
    assert cli.get(f"/brasil/abrigos/{cena['a1']}", headers=como(cena["g1"])).json()["presentes"] == 3
    assert [a["presentes"] for a in cli.get("/brasil/abrigos", headers=como(cena["g1"])).json()] == [3]
    conn = db.conectar(cena["rotas"].CFG)
    assert conn.execute("SELECT COUNT(*) FROM familias WHERE abrigo_id=?", (cena["a1"],)).fetchone()[0] == 1
    conn.close()


def test_pessoa_sozinha_nao_cria_familia(cena):
    cli = cena["cli"]
    r = chegar(cli, cena["g1"], cena["a1"], [{"nome": "Sozinho Fictício", "nome_mae": "Mãe Fictícia"}], entrada_em="2026-11-18T08:30")
    assert r.status_code == 200
    p = r.json()["pessoas"][0]
    assert r.json()["familia_id"] is None and p["familia_id"] is None and p["entrada_em"] == "2026-11-18T11:30:00+00:00"


def test_lista_agrupa_por_familia_e_saida_baixa_a_lotacao(cena):
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    chegar(cli, g1, a1, [{"nome": "Sozinho Fictício", "nome_mae": "Mãe Fictícia"}])
    lista = cli.get(f"/brasil/abrigos/{a1}/pessoas", headers=como(g1)).json()
    assert sorted(len(g["pessoas"]) for g in lista["grupos"]) == [1, 3] and lista["lotacao"]["presentes"] == 4
    pid = cena["chegada"]["pessoas"][0]["id"]
    r = cli.post(f"/brasil/abrigados/{pid}/saida", json={}, headers=como(g1))
    assert r.status_code == 200 and r.json()["pessoa"]["presente"] is False and r.json()["lotacao"]["presentes"] == 3
    assert cli.post(f"/brasil/abrigados/{pid}/saida", json={}, headers=como(g1)).status_code == 409
    presentes = cli.get(f"/brasil/abrigos/{a1}/pessoas", headers=como(g1)).json()
    assert pid not in [p["id"] for g in presentes["grupos"] for p in g["pessoas"]]
    todos = cli.get(f"/brasil/abrigos/{a1}/pessoas", params={"presentes": 0}, headers=como(g1)).json()
    assert pid in [p["id"] for g in todos["grupos"] for p in g["pessoas"]]


def test_uma_saida_da_familia_de_tres_deixa_2(cena):
    cli, g1 = cena["cli"], cena["g1"]
    pid = cena["chegada"]["pessoas"][2]["id"]
    assert cli.post(f"/brasil/abrigados/{pid}/saida", headers=como(g1)).json()["lotacao"]["presentes"] == 2


def test_saida_antes_da_entrada_422(cena):
    cli, g1 = cena["cli"], cena["g1"]
    pid = cena["chegada"]["pessoas"][0]["id"]
    r = cli.post(f"/brasil/abrigados/{pid}/saida", json={"saida_em": "2020-01-01T00:00"}, headers=como(g1))
    assert r.status_code == 422 and r.json()["detail"] == "A saída não pode ser antes da entrada"
    assert cli.get(f"/brasil/abrigos/{cena['a1']}/lotacao", headers=como(g1)).json()["presentes"] == 3  # continua presente


def _ativar(cli, uid, aid, ativo: bool):
    corpo = {"nome": "Abrigo Ginásio Fictício", "endereco": "", **POA, "capacidade": 120, "tipo": "temporario", "ativo": ativo}
    r = cli.put(f"/brasil/abrigos/{aid}", json=corpo, headers=como(uid))
    assert r.status_code == 200 and r.json()["ativo"] is ativo, r.text


def test_chegada_em_abrigo_inativo_409_e_nada_e_gravado(cena):
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    _ativar(cli, g1, a1, False)
    r = chegar(cli, g1, a1, [{"nome": "Inativo Fictício", "nome_mae": "Mãe Fictícia"}, {"nome": "Outro Fictício", "nome_mae": "Mãe Fictícia"}])
    assert r.status_code == 409
    assert r.json()["detail"] == "Este abrigo está inativo. Reative o abrigo antes de registrar chegadas."
    conn = db.conectar(cena["rotas"].CFG)
    assert conn.execute("SELECT COUNT(*) FROM abrigados WHERE abrigo_id=?", (a1,)).fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM familias WHERE abrigo_id=?", (a1,)).fetchone()[0] == 1
    conn.close()


def test_abrigo_criado_inativo_tambem_recusa_chegada(api):
    cli, _ = api
    g = cli.post("/brasil/dev/usuario/gestor").json()["id"]
    aid = abrigo(cli, g, ativo=False)
    assert chegar(cli, g, aid, [{"nome": "Inativo Fictício", "nome_mae": "Mãe Fictícia"}]).status_code == 409
    assert cli.get(f"/brasil/abrigos/{aid}/lotacao", headers=como(g)).json()["presentes"] == 0


def test_reativar_o_abrigo_volta_a_aceitar_chegada(cena):
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    pessoa = [{"nome": "Reativado Fictício", "nome_mae": "Mãe Fictícia"}]
    _ativar(cli, g1, a1, False)
    assert chegar(cli, g1, a1, pessoa).status_code == 409
    _ativar(cli, g1, a1, True)
    r = chegar(cli, g1, a1, pessoa)
    assert r.status_code == 200, r.text
    assert r.json()["lotacao"]["presentes"] == 4


def test_saida_de_abrigo_inativo_continua_valendo(cena):
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    _ativar(cli, g1, a1, False)
    pid = cena["chegada"]["pessoas"][0]["id"]
    r = cli.post(f"/brasil/abrigados/{pid}/saida", headers=como(g1))
    assert r.status_code == 200, r.text
    assert r.json()["pessoa"]["presente"] is False and r.json()["lotacao"]["presentes"] == 2


def test_abrigo_inativo_de_outro_gestor_continua_404(cena):
    cli = cena["cli"]
    _ativar(cli, cena["g2"], cena["a2"], False)
    assert chegar(cli, cena["g1"], cena["a2"], [{"nome": "Intruso Fictício", "nome_mae": "Mãe Fictícia"}]).status_code == 404


def test_entrada_no_futuro_422_com_folga_de_10_minutos(cena):
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    agora = datetime.now(timezone.utc)
    pessoa = [{"nome": "Futuro Fictício", "nome_mae": "Mãe Fictícia"}]
    r = chegar(cli, g1, a1, pessoa, entrada_em=(agora + timedelta(hours=1)).isoformat())
    assert r.status_code == 422 and "futuro" in r.json()["detail"]
    assert cli.get(f"/brasil/abrigos/{a1}/lotacao", headers=como(g1)).json()["presentes"] == 3
    assert chegar(cli, g1, a1, pessoa, entrada_em=(agora + timedelta(minutes=5)).isoformat()).status_code == 200


def test_datas_sem_fuso_sao_horario_de_brasilia_e_ficam_em_utc(cena):
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    r = chegar(cli, g1, a1, [{"nome": "Fuso Fictício", "nome_mae": "Mãe Fictícia"}], entrada_em="2026-11-18T10:00-03:00")
    assert r.status_code == 200, r.text
    p = r.json()["pessoas"][0]
    assert p["entrada_em"] == "2026-11-18T13:00:00+00:00"
    s = cli.post(f"/brasil/abrigados/{p['id']}/saida", json={"saida_em": "2026-11-18T11:00"}, headers=como(g1))
    assert s.status_code == 200, s.text
    assert s.json()["pessoa"]["saida_em"] == "2026-11-18T14:00:00+00:00"
    # entrada 13:00 UTC (10:00 em Brasília); saída "12:30" sem fuso é 15:30 UTC, depois da entrada
    r2 = chegar(cli, g1, a1, [{"nome": "Fuso Dois Fictício", "nome_mae": "Mãe Fictícia"}], entrada_em="2026-11-18T13:00:00Z")
    pid = r2.json()["pessoas"][0]["id"]
    s2 = cli.post(f"/brasil/abrigados/{pid}/saida", json={"saida_em": "2026-11-18T12:30"}, headers=como(g1))
    assert s2.status_code == 200 and s2.json()["pessoa"]["saida_em"] == "2026-11-18T15:30:00+00:00"


@pytest.mark.parametrize("pessoa", [
    {"nome": "Fulano Fictício", "nome_mae": "Mãe Fictícia", "cpf": "1234567890"},     # 10 dígitos
    {"nome": "Fulano Fictício", "nome_mae": "Mãe Fictícia", "cpf": "123456789012"},   # 12 dígitos
    {"nome": "   ", "nome_mae": "Mãe Fictícia"},
    {"nome": "Fulano Fictício", "nome_mae": ""},
    {"nome": "Fulano Fictício"},
    {"nome": "Fulano Fictício", "nome_mae": "Mãe Fictícia", "necessidades": ["voo"]},
])
def test_pessoa_invalida_422_e_nada_e_gravado(cena, pessoa):
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    r = chegar(cli, g1, a1, [{"nome": "Ok Fictício", "nome_mae": "Mãe Ok"}, pessoa])
    assert r.status_code == 422
    assert cli.get(f"/brasil/abrigos/{a1}/lotacao", headers=como(g1)).json()["presentes"] == 3


def test_chegada_sem_pessoas_e_data_invalida_422(cena):
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    assert chegar(cli, g1, a1, []).status_code == 422
    assert chegar(cli, g1, a1, [{"nome": "Ok Fictício", "nome_mae": "Mãe Ok"}], entrada_em="ontem").status_code == 422


def test_cpf_em_branco_ou_so_pontuacao_vira_nulo(cena):
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    r = chegar(cli, g1, a1, [{"nome": "Sem Cpf Fictício", "nome_mae": "Mãe Fictícia", "cpf": " .- "}])
    assert r.status_code == 200 and r.json()["pessoas"][0]["cpf"] is None


@pytest.mark.parametrize("cpf", ["123.456.789-0a", "abc12345678901", "123/456/789-01", "１２３４５６７８９０１"])
def test_cpf_com_letra_ou_outro_caractere_422(cena, cpf):
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    r = chegar(cli, g1, a1, [{"nome": "Letra Fictícia", "nome_mae": "Mãe Fictícia", "cpf": cpf}])
    assert r.status_code == 422 and "só números" in r.json()["detail"]
    assert cli.get(f"/brasil/abrigos/{a1}/lotacao", headers=como(g1)).json()["presentes"] == 3


def test_cpf_com_pontos_hifen_e_espacos_vale(cena):
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    r = chegar(cli, g1, a1, [{"nome": "Pontuado Fictício", "nome_mae": "Mãe Fictícia", "cpf": " 123.456.789 - 01 "}])
    assert r.status_code == 200 and r.json()["pessoas"][0]["cpf"] == "12345678901"


def test_passar_da_capacidade_avisa_mas_registra(api):
    cli, _ = api
    g1 = cli.post("/brasil/dev/usuario/gestor").json()["id"]
    aid = abrigo(cli, g1, capacidade=2)
    r = chegar(cli, g1, aid, FAMILIA)
    assert r.status_code == 200
    assert r.json()["lotacao"] == {"capacidade": 2, "presentes": 3, "livres": 0, "lotado": True, "acima": 1}
    assert any("capacidade" in a for a in r.json()["avisos"])


def test_cpf_repetido_no_mesmo_abrigo_avisa_sem_bloquear(cena):
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    r = chegar(cli, g1, a1, [{"nome": "Outro Fictício", "nome_mae": "Outra Mãe", "cpf": "12345678901"}])
    assert r.status_code == 200 and any("CPF" in a for a in r.json()["avisos"])
    # CPF igual em outro abrigo não é aviso (o gestor não vê os outros)
    r2 = chegar(cli, cena["g2"], cena["a2"], [{"nome": "Outro Fictício", "nome_mae": "Outra Mãe", "cpf": "12345678901"}])
    assert r2.json()["avisos"] == []


def test_nome_busca_sem_acento_e_minusculo():
    assert nome_busca("  JOÃO  Fictício ") == "joao ficticio"


# ── busca ────────────────────────────────────────────────────────────
def busca(cli, uid, nome):
    return cli.get("/brasil/abrigados/busca", params={"nome": nome}, headers=como(uid))


def test_busca_de_gestor_nao_verificado_so_nos_proprios_abrigos(cena):
    cli, g1 = cena["cli"], cena["g1"]
    r = busca(cli, g1, "fictici").json()
    assert r["escopo"] == "meus_abrigos"
    nomes = [x["nome"] for x in r["resultados"]]
    assert "João Fictício da Silva" in nomes and "Joana Fictícia Pereira" not in nomes


def test_busca_sem_acento_acha_com_acento(cena):
    r = busca(cena["cli"], cena["g1"], "joao").json()
    assert [x["nome"] for x in r["resultados"]] == ["João Fictício da Silva"]
    assert busca(cena["cli"], cena["g1"], "JOÃO fic").json()["resultados"][0]["nome"] == "João Fictício da Silva"


def test_busca_depois_de_verificar_acha_nos_dois_e_cpf_so_dos_proprios(cena):
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    assert cli.post(f"/brasil/dev/abrigos/{a1}/verificar", headers=como(g1)).json()["verificado"] is True
    r = busca(cli, g1, "jo").json()
    assert r["escopo"] == "todos"
    por_nome = {x["nome"]: x for x in r["resultados"]}
    assert set(por_nome) == {"João Fictício da Silva", "Joana Fictícia Pereira"}
    meu, outro = por_nome["João Fictício da Silva"], por_nome["Joana Fictícia Pereira"]
    assert meu["cpf"] == "12345678901" and meu["meu_abrigo"] is True
    assert "cpf" not in outro and outro["meu_abrigo"] is False and "11122233344" not in str(r)
    # ADR 0008: de outro abrigo, só o nome e o caminho de contato
    assert outro == {"nome": "Joana Fictícia Pereira", "meu_abrigo": False,
                     "contato": "Entre em contato com a coordenação regional."}
    for vazado in ("Clara Fictícia Pereira", "Escola Fictícia de Canoas", "Canoas"):
        assert vazado not in r_texto(cli, g1, "joana")
    # gestor2 (não verificado) continua só nos dele
    r2 = busca(cli, cena["g2"], "jo").json()
    assert r2["escopo"] == "meus_abrigos" and [x["nome"] for x in r2["resultados"]] == ["Joana Fictícia Pereira"]


def test_abrigo_sensivel_de_outro_gestor_nunca_aparece_na_busca(cena):
    """ADR 0008: abrigo de proteção (sensível) fica fora da busca entre abrigos; o próprio gestor ainda acha."""
    cli, g1, g2 = cena["cli"], cena["g1"], cena["g2"]
    casa = abrigo(cli, g2, nome="Casa de Acolhimento Fictícia", sensivel=True, **CANOAS)
    assert chegar(cli, g2, casa, [{"nome": "Joaquina Fictícia Protegida", "nome_mae": "Mãe Fictícia"}]).status_code == 200
    cli.post(f"/brasil/dev/abrigos/{cena['a1']}/verificar", headers=como(g1))
    r = busca(cli, g1, "joaquina")
    assert r.json()["escopo"] == "todos" and r.json()["resultados"] == [] and "Protegida" not in r.text
    assert sorted(x["nome"] for x in busca(cli, g1, "jo").json()["resultados"]) == ["Joana Fictícia Pereira", "João Fictício da Silva"]
    # o gestor da casa acha a própria gente, verificado ou não
    for _ in range(2):
        [x] = busca(cli, g2, "joaquina").json()["resultados"]
        assert x["nome"] == "Joaquina Fictícia Protegida" and x["meu_abrigo"] is True and x["abrigo"]["id"] == casa
        cli.post(f"/brasil/dev/abrigos/{casa}/verificar", headers=como(g2))


CHAVES_MEU_ABRIGO = {"nome", "nome_mae", "cpf", "abrigo", "entrada_em", "saida_em", "presente", "meu_abrigo"}
CHAVES_OUTRO_ABRIGO = {"nome", "meu_abrigo", "contato"}


def r_texto(cli, uid, nome) -> str:
    return busca(cli, uid, nome).text


def test_resultado_de_outro_abrigo_tem_so_nome_e_contato(cena):
    cli, g1, g2 = cena["cli"], cena["g1"], cena["g2"]
    cli.post(f"/brasil/dev/abrigos/{cena['a2']}/verificar", headers=como(g2))
    r = busca(cli, g2, "fictici").json()
    assert r["escopo"] == "todos" and r["resultados"]
    for x in r["resultados"]:
        assert set(x) == (CHAVES_MEU_ABRIGO if x["meu_abrigo"] else CHAVES_OUTRO_ABRIGO), x
    outros = [x for x in r["resultados"] if not x["meu_abrigo"]]
    assert sorted(x["nome"] for x in outros) == ["Ana Fictícia da Silva", "João Fictício da Silva", "Pedrinho Fictício da Silva"]
    assert {x["contato"] for x in outros} == {"Entre em contato com a coordenação regional."}
    texto = r_texto(cli, g2, "silva")  # só gente do abrigo de g1
    for vazado in ("Maria Fictícia da Silva", "Rosa Fictícia Souza", "Abrigo Ginásio Fictício", "Porto Alegre",
                   "12345678901", "98765432100", "nome_mae", "entrada_em", "saida_em", "presente", '"abrigo"'):
        assert vazado not in texto, vazado


def test_quem_saiu_some_da_busca_de_outros_abrigos_e_continua_para_o_dono(cena):
    cli, g1, g2 = cena["cli"], cena["g1"], cena["g2"]
    cli.post(f"/brasil/dev/abrigos/{cena['a2']}/verificar", headers=como(g2))
    assert [x["nome"] for x in busca(cli, g2, "joao").json()["resultados"]] == ["João Fictício da Silva"]
    cli.post(f"/brasil/abrigados/{cena['chegada']['pessoas'][0]['id']}/saida", headers=como(g1))
    assert busca(cli, g2, "joao").json()["resultados"] == []
    [x] = busca(cli, g1, "joao").json()["resultados"]
    assert x["meu_abrigo"] is True and x["presente"] is False and x["saida_em"]


def test_visao_do_proprio_gestor_continua_completa(cena):
    """O que o dono vê dos próprios abrigos não muda com a ADR 0008: CPF, datas, abrigo e município."""
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    entrada = cena["chegada"]["pessoas"][0]["entrada_em"]
    for verificar in (False, True):
        if verificar:
            cli.post(f"/brasil/dev/abrigos/{a1}/verificar", headers=como(g1))
        [x] = busca(cli, g1, "joao").json()["resultados"]
        assert x == {"nome": "João Fictício da Silva", "nome_mae": "Maria Fictícia da Silva", "cpf": "12345678901",
                     "abrigo": {"id": a1, "nome": "Abrigo Ginásio Fictício", "municipio": "Porto Alegre"},
                     "entrada_em": entrada, "saida_em": None, "presente": True, "meu_abrigo": True}
    pessoas = cli.get(f"/brasil/abrigos/{a1}/pessoas", headers=como(g1)).json()["grupos"][0]["pessoas"]
    assert [p["cpf"] for p in pessoas] == ["12345678901", "98765432100", None]


def test_busca_mostra_quem_ja_saiu_como_nao_presente(cena):
    cli, g1 = cena["cli"], cena["g1"]
    cli.post(f"/brasil/abrigados/{cena['chegada']['pessoas'][0]['id']}/saida", headers=como(g1))
    [x] = busca(cli, g1, "joao").json()["resultados"]
    assert x["presente"] is False and x["saida_em"]


@pytest.mark.parametrize("nome", ["", "a", "  b  ", "%"])
def test_busca_curta_422(cena, nome):
    assert busca(cena["cli"], cena["g1"], nome).status_code == 422


def test_busca_trata_curinga_como_texto(cena):
    # % e _ são pontuação: viram espaço, nunca curinga do LIKE
    assert busca(cena["cli"], cena["g1"], "%%").status_code == 422
    assert busca(cena["cli"], cena["g1"], "__").status_code == 422
    assert busca(cena["cli"], cena["g1"], "jo%o").json()["resultados"] == []
    assert busca(cena["cli"], cena["g1"], "jo_o").json()["resultados"] == []


def test_nome_busca_tira_pontuacao():
    assert nome_busca("Ana D'Ávila") == nome_busca("Ana D’Ávila") == "ana davila"
    assert nome_busca("Maria-Clara  S. Lima") == "maria clara s lima"


def test_busca_ignora_pontuacao(cena):
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    r = chegar(cli, g1, a1, [{"nome": "Ana D'Ávila Fictícia", "nome_mae": "Mãe Fictícia"},
                             {"nome": "Maria-Clara Fictícia", "nome_mae": "Mãe Fictícia"}])
    assert r.status_code == 200, r.text
    for termo, nome in (("davila", "Ana D'Ávila Fictícia"), ("d’avila", "Ana D'Ávila Fictícia"),
                        ("maria clara", "Maria-Clara Fictícia"), ("maria-clara", "Maria-Clara Fictícia")):
        assert [x["nome"] for x in busca(cli, g1, termo).json()["resultados"]] == [nome], termo


# ── auditoria da busca entre abrigos (ADR 0008) ──────────────────────
def log_de_buscas(rotas) -> list:
    conn = db.conectar(rotas.CFG)
    try:
        return [dict(r) for r in conn.execute("SELECT user_id, consulta, buscado_em, resultados FROM buscas_abrigados_log ORDER BY id")]
    finally:
        conn.close()


def test_toda_busca_entre_abrigos_fica_registrada_mesmo_sem_resultado(cena):
    cli, g1 = cena["cli"], cena["g1"]
    cli.post(f"/brasil/dev/abrigos/{cena['a1']}/verificar", headers=como(g1))
    antes = datetime.now(timezone.utc).replace(microsecond=0)
    assert len(busca(cli, g1, "  Jo ").json()["resultados"]) == 2
    assert busca(cli, g1, "ninguem ficticio").json()["resultados"] == []
    assert busca(cli, g1, "a").status_code == 422  # busca recusada não roda, não registra
    log = log_de_buscas(cena["rotas"])
    assert [(x["user_id"], x["consulta"], x["resultados"]) for x in log] == [(g1, "Jo", 2), (g1, "ninguem ficticio", 0)]
    for x in log:
        quando = datetime.fromisoformat(x["buscado_em"])
        assert quando.utcoffset() == timedelta(0) and antes <= quando <= datetime.now(timezone.utc)


def test_busca_so_nos_proprios_abrigos_nao_e_registrada(cena):
    cli = cena["cli"]
    assert busca(cli, cena["g1"], "joao").json()["escopo"] == "meus_abrigos"
    assert busca(cli, cena["g2"], "nada").json()["escopo"] == "meus_abrigos"
    assert log_de_buscas(cena["rotas"]) == []


def suspeito(caminho: str) -> bool:
    """Caminho que poderia expor o registro de buscas (`/brasil/login` não conta)."""
    partes = caminho.lower().replace("_", "/").replace("-", "/").strip("/").split("/")
    return any(p in ("log", "logs", "auditoria", "buscas", "historico") for p in partes)


def test_registro_de_buscas_nao_sai_por_nenhuma_rota(cena):
    """Só gravado: nenhuma rota da API nem ação da POLITICA lê a tabela, e nenhum perfil vê o que foi buscado."""
    import os
    from fastapi import FastAPI
    cli, rotas, g1 = cena["cli"], cena["rotas"], cena["g1"]
    cli.post(f"/brasil/dev/abrigos/{cena['a1']}/verificar", headers=como(g1))
    busca(cli, g1, "Rastro Fictício Auditado")
    assert log_de_buscas(rotas)[0]["consulta"] == "Rastro Fictício Auditado"
    app = FastAPI()
    app.include_router(rotas.router)
    caminhos = list(app.openapi()["paths"])
    assert "/brasil/abrigados/busca" in caminhos and not [c for c in caminhos if suspeito(c)]
    raiz = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    # (POLITICA e rotas do Flask: test_frontend.py::test_registro_de_buscas_nao_tem_acao_nem_pagina)
    # só db.py (esquema), merge_brasil.py e o INSERT em abrigados.py citam a tabela
    pasta = os.path.join(raiz, "middleware", "brasil")
    citam = {f for f in os.listdir(pasta) if f.endswith(".py")
             and "buscas_abrigados_log" in open(os.path.join(pasta, f), encoding="utf-8").read()}
    assert citam == {"db.py", "merge_brasil.py", "abrigados.py"}
    fonte = open(os.path.join(pasta, "abrigados.py"), encoding="utf-8").read()
    assert fonte.count("buscas_abrigados_log") == 2 and "INSERT INTO buscas_abrigados_log" in fonte  # docstring + INSERT
    for base, _, arquivos in os.walk(os.path.join(raiz, "frontend", "brasil")):
        for f in arquivos:
            if f.endswith((".py", ".js", ".html")) and "tests" not in base:
                assert "buscas_abrigados_log" not in open(os.path.join(base, f), encoding="utf-8").read(), f
    for perfil in ("voluntario", "ong", "admin", "gestor", "gestor2"):
        uid = cli.post(f"/brasil/dev/usuario/{perfil}").json()["id"]
        h = como(uid)
        for r in (cli.get("/brasil/abrigos", headers=h), cli.get(f"/brasil/usuarios/{uid}", headers=h),
                  cli.get("/brasil/crises", headers=h), busca(cli, uid, "rastro")):
            assert "Rastro" not in r.text and "buscado_em" not in r.text, (perfil, r.url)


# ── privacidade (Done-when #4) ───────────────────────────────────────
def _rotas_de_pessoas(c):
    pid = c["chegada"]["pessoas"][0]["id"]
    return [
        ("POST", f"/brasil/abrigos/{c['a1']}/chegadas", {"pessoas": [{"nome": "Intruso Fictício", "nome_mae": "Mãe"}]}),
        ("GET", f"/brasil/abrigos/{c['a1']}/pessoas", None),
        ("POST", f"/brasil/abrigados/{pid}/saida", {}),
        ("GET", f"/brasil/abrigos/{c['a1']}/lotacao", None),
        ("GET", "/brasil/abrigados/busca?nome=joao", None),
    ]


@pytest.mark.parametrize("perfil", ["voluntario", "ong", "admin"])
@pytest.mark.parametrize("i", range(5))
def test_outros_perfis_recebem_403_em_toda_rota_de_pessoas(cena, perfil, i):
    cli = cena["cli"]
    uid = cli.post(f"/brasil/dev/usuario/{perfil}").json()["id"]
    metodo, caminho, corpo = _rotas_de_pessoas(cena)[i]
    r = cli.request(metodo, caminho, json=corpo, headers=como(uid))
    assert r.status_code == 403 and "Fictíci" not in r.text
    assert cli.request(metodo, caminho, json=corpo).status_code == 401  # sem identidade


@pytest.mark.parametrize("i", range(4))  # a busca não é por abrigo: o escopo é testado acima
def test_outro_gestor_recebe_404_nas_pessoas_do_abrigo_alheio(cena, i):
    cli = cena["cli"]
    metodo, caminho, corpo = _rotas_de_pessoas(cena)[i]
    r = cli.request(metodo, caminho, json=corpo, headers=como(cena["g2"]))
    assert r.status_code == 404 and "Fictíci" not in r.text
    assert cli.get(f"/brasil/abrigos/{cena['a1']}/lotacao", headers=como(cena["g1"])).json()["presentes"] == 3
    assert cli.get(f"/brasil/abrigos/{cena['a1']}/pessoas", headers=como(cena["g1"])).json()["grupos"][0]["pessoas"][0]["presente"]


def test_saida_de_pessoa_inexistente_404(cena):
    assert cena["cli"].post("/brasil/abrigados/99999/saida", headers=como(cena["g1"])).status_code == 404


@pytest.mark.parametrize("perfil", ["voluntario", "ong", "admin"])
def test_dados_de_abrigados_nao_aparecem_para_outros_perfis(cena, perfil):
    cli, rotas = cena["cli"], cena["rotas"]
    conn = db.conectar(rotas.CFG)
    conn.execute("INSERT INTO crises (id, title, country, lat, lon, severity, uf) VALUES ('cemaden-x','Chuva fictícia','Brasil',-30.03,-51.22,3,'RS')")
    conn.execute("INSERT INTO abrigo_crises (abrigo_id, crisis_id) VALUES (?, 'cemaden-x')", (cena["a1"],))
    conn.commit()
    conn.close()
    uid = cli.post(f"/brasil/dev/usuario/{perfil}").json()["id"]
    h = como(uid)
    respostas = [cli.get("/brasil/crises", headers=h), cli.get("/brasil/crises"), cli.get("/brasil/abrigos", headers=h),
                 cli.get(f"/brasil/usuarios/{uid}", headers=h)]
    if perfil != "admin":
        respostas.append(cli.get(f"/brasil/usuarios/{uid}/inscricoes", headers=h))
    for r in respostas:
        for dado in DADOS_PESSOAIS:
            assert dado not in r.text, (r.url, dado)


def test_listagem_de_abrigos_do_gestor_so_tem_a_contagem(cena):
    r = cena["cli"].get("/brasil/abrigos", headers=como(cena["g1"]))
    for dado in DADOS_PESSOAIS:
        assert dado not in r.text
    assert r.json()[0]["presentes"] == 3


def test_rotas_de_pessoas_nao_imprimem_dados(cena, capsys, caplog):
    cli, g1, a1 = cena["cli"], cena["g1"], cena["a1"]
    caplog.set_level("DEBUG")
    chegar(cli, g1, a1, [{"nome": "Silencioso Fictício", "nome_mae": "Mãe Silenciosa", "cpf": "55566677788"}])
    cli.get(f"/brasil/abrigos/{a1}/pessoas", headers=como(g1))
    busca(cli, g1, "silencioso")
    saida = capsys.readouterr()
    texto = saida.out + saida.err + caplog.text
    for dado in ("Silencioso", "Mãe Silenciosa", "55566677788"):
        assert dado not in texto
