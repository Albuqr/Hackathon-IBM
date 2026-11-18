"""Pessoas abrigadas (ADR 0006): regras de chegada/saída, lotação, busca e privacidade. Só pessoas fictícias."""
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
    assert r.json()["familia_id"] is None and p["familia_id"] is None and p["entrada_em"] == "2026-11-18T08:30:00"


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
    assert cli.post(f"/brasil/abrigados/{pid}/saida", json={"saida_em": "2020-01-01T00:00"}, headers=como(g1)).status_code == 422


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
    assert outro["nome_mae"] == "Clara Fictícia Pereira" and outro["presente"] is True
    assert outro["abrigo"] == {"id": cena["a2"], "nome": "Escola Fictícia de Canoas", "municipio": "Canoas"}
    # gestor2 (não verificado) continua só nos dele
    r2 = busca(cli, cena["g2"], "jo").json()
    assert r2["escopo"] == "meus_abrigos" and [x["nome"] for x in r2["resultados"]] == ["Joana Fictícia Pereira"]


def test_busca_mostra_quem_ja_saiu_como_nao_presente(cena):
    cli, g1 = cena["cli"], cena["g1"]
    cli.post(f"/brasil/abrigados/{cena['chegada']['pessoas'][0]['id']}/saida", headers=como(g1))
    [x] = busca(cli, g1, "joao").json()["resultados"]
    assert x["presente"] is False and x["saida_em"]


@pytest.mark.parametrize("nome", ["", "a", "  b  ", "%"])
def test_busca_curta_422(cena, nome):
    assert busca(cena["cli"], cena["g1"], nome).status_code == 422


def test_busca_trata_curinga_como_texto(cena):
    assert busca(cena["cli"], cena["g1"], "%%").json()["resultados"] == []
    assert busca(cena["cli"], cena["g1"], "__").json()["resultados"] == []


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
