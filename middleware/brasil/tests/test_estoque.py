"""Estoque e necessidades do abrigo, lista compartilhada de itens e agente de duplicados (ADR 0007)."""
import pytest

from middleware.brasil import db, orquestracao
from middleware.brasil.estoque import duplicados, normalizar

POA = {"lat": -30.0346, "lon": -51.2177}


def como(uid) -> dict:
    return {"X-Brasil-Usuario": str(uid)}


@pytest.fixture
def abrigo(api):
    cli, rotas = api
    g1 = cli.post("/brasil/dev/usuario/gestor").json()["id"]
    g2 = cli.post("/brasil/dev/usuario/gestor2").json()["id"]
    a = cli.post("/brasil/abrigos", json={"nome": "Ginásio Fictício", **POA, "capacidade": 80, "tipo": "temporario"},
                 headers=como(g1)).json()
    return cli, rotas, g1, g2, a["id"]


def item(cli, uid, nome) -> dict:
    sug = cli.get("/brasil/itens/sugestoes", params={"q": nome}, headers=como(uid)).json()
    return next(i for i in sug["itens"] if normalizar(i["nome"]) == normalizar(nome))


def test_lista_base_tem_os_quatro_grupos_e_profissionais_e_veiculos_so_pedido(abrigo):
    cli, rotas, g1, *_ = abrigo
    grupos = cli.get("/brasil/itens/grupos", headers=como(g1)).json()
    assert [g["nome"] for g in grupos] == ["Sustento", "Profissionais", "Energia e Mobilidade", "Estrutura e Ativos"]
    conn = db.conectar(rotas.CFG)
    try:
        base = {r["nome"]: dict(r) for r in conn.execute("SELECT nome, nome_busca, grupo, unidade, so_necessidade FROM itens")}
    finally:
        conn.close()
    assert {b["grupo"] for b in base.values()} == {"sustento", "profissionais", "energia_mobilidade", "estrutura_ativos"}
    assert all(normalizar(n) == b["nome_busca"] for n, b in base.items())  # a semente usa a mesma normalização
    assert base["Água"]["so_necessidade"] == 0 and base["Gasolina"]["unidade"] == "litros"
    for n in ("Equipe de saúde", "Bombeiros", "Polícia", "Carro", "Caminhão", "Ambulância"):
        assert base[n]["so_necessidade"] == 1, n
    for n in ("Gasolina", "Etanol", "Diesel", "AVGAS", "Colchões", "Cobertores", "Roupas", "Ferramentas", "Cesta básica"):
        assert base[n]["so_necessidade"] == 0, n
    # semente idempotente: reconectar não duplica
    db._prontos.clear()
    conn = db.conectar(rotas.CFG)
    assert conn.execute("SELECT COUNT(*) FROM itens").fetchone()[0] == len(base)
    conn.close()


def test_agua_urgente_com_quantidade_e_colchoes_sobrando(abrigo):
    cli, _, g1, _, aid = abrigo
    agua, colchoes = item(cli, g1, "Água"), item(cli, g1, "Colchões")
    r = cli.put(f"/brasil/abrigos/{aid}/estoque/{agua['id']}", json={"status": "urgente", "quantidade": 500}, headers=como(g1))
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["quantidade"], r.json()["unidade"], r.json()["grupo_nome"]) == ("urgente", 500, "litros", "Sustento")
    assert cli.put(f"/brasil/abrigos/{aid}/estoque/{colchoes['id']}", json={"status": "sobrando"}, headers=como(g1)).status_code == 200
    est = {x["nome"]: x for x in cli.get(f"/brasil/abrigos/{aid}/estoque", headers=como(g1)).json()}
    assert est["Água"]["status_nome"] == "Urgente" and est["Colchões"]["status"] == "sobrando" and est["Colchões"]["quantidade"] is None
    # atualizar troca o status; remover tira só deste abrigo
    cli.put(f"/brasil/abrigos/{aid}/estoque/{agua['id']}", json={"status": "ok", "quantidade": 0}, headers=como(g1))
    assert {x["nome"]: x["status"] for x in cli.get(f"/brasil/abrigos/{aid}/estoque", headers=como(g1)).json()}["Água"] == "ok"
    assert cli.delete(f"/brasil/abrigos/{aid}/estoque/{agua['id']}", headers=como(g1)).json()["removido"] is True
    assert [x["nome"] for x in cli.get(f"/brasil/abrigos/{aid}/estoque", headers=como(g1)).json()] == ["Colchões"]
    assert item(cli, g1, "Água")["id"] == agua["id"]


@pytest.mark.parametrize("corpo", [{"status": "talvez"}, {"status": "ok", "quantidade": -1}])
def test_status_ou_quantidade_invalidos_422(abrigo, corpo):
    cli, _, g1, _, aid = abrigo
    agua = item(cli, g1, "Água")
    assert cli.put(f"/brasil/abrigos/{aid}/estoque/{agua['id']}", json=corpo, headers=como(g1)).status_code == 422


def test_item_inexistente_404(abrigo):
    cli, _, g1, _, aid = abrigo
    assert cli.put(f"/brasil/abrigos/{aid}/estoque/9999", json={"status": "ok"}, headers=como(g1)).status_code == 404


@pytest.mark.parametrize("nome", ["Bombeiros", "Ambulância"])
def test_profissionais_e_veiculos_so_pedido_com_quantidade(abrigo, nome):
    cli, _, g1, _, aid = abrigo
    it = item(cli, g1, nome)
    url = f"/brasil/abrigos/{aid}/estoque/{it['id']}"
    for st in ("ok", "sobrando"):
        r = cli.put(url, json={"status": st, "quantidade": 2}, headers=como(g1))
        assert r.status_code == 422 and "só pedidos" in r.json()["detail"]
    for q in (None, 0):
        r = cli.put(url, json={"status": "urgente", "quantidade": q}, headers=como(g1))
        assert r.status_code == 422 and "quantos precisa" in r.json()["detail"]
    r = cli.put(url, json={"status": "urgente", "quantidade": 3}, headers=como(g1))
    assert r.status_code == 200 and r.json()["so_necessidade"] is True
    assert cli.put(url, json={"status": "precisa", "quantidade": 1}, headers=como(g1)).status_code == 200


def test_item_novo_aparece_para_outro_gestor_ao_digitar(abrigo):
    cli, _, g1, g2, _ = abrigo
    r = cli.post("/brasil/itens", json={"nome": "Fraldas infantis", "grupo": "sustento", "unidade": "pacotes"}, headers=como(g1))
    assert r.status_code == 200 and r.json()["existente"] is False
    novo = r.json()["item"]
    assert (novo["grupo"], novo["unidade"], novo["so_necessidade"]) == ("sustento", "pacotes", False)
    sug = cli.get("/brasil/itens/sugestoes", params={"q": "fral"}, headers=como(g2)).json()
    assert sug["itens"][0]["id"] == novo["id"] and sug["exato"] is None
    assert cli.get("/brasil/itens/sugestoes", params={"q": "INFANTIS"}, headers=como(g2)).json()["itens"][0]["id"] == novo["id"]
    # o mesmo nome normalizado devolve o que existe, sem criar outro
    de_novo = cli.post("/brasil/itens", json={"nome": " fraldas  INFANTÍS ", "grupo": "estrutura_ativos", "unidade": "un"}, headers=como(g2)).json()
    assert de_novo["existente"] is True and de_novo["item"]["id"] == novo["id"] and de_novo["item"]["grupo"] == "sustento"


def test_sugestoes_comecam_pelo_inicio_do_nome_e_vazio_nao_busca(abrigo):
    cli, _, g1, *_ = abrigo
    cli.post("/brasil/itens", json={"nome": "Garrafa de água", "grupo": "sustento", "unidade": "unidades"}, headers=como(g1))
    sug = cli.get("/brasil/itens/sugestoes", params={"q": "agua"}, headers=como(g1)).json()
    assert [i["nome"] for i in sug["itens"]][:2] == ["Água", "Garrafa de água"]
    assert sug["exato"] == sug["itens"][0]["id"]
    assert cli.get("/brasil/itens/sugestoes", params={"q": "  "}, headers=como(g1)).json() == {"itens": [], "exato": None, "possiveis_duplicados": []}


def test_grupo_profissionais_forca_so_necessidade_e_veiculo_escolhe(abrigo):
    cli, _, g1, *_ = abrigo
    p = cli.post("/brasil/itens", json={"nome": "Psicólogos", "grupo": "profissionais", "unidade": "pessoas", "so_necessidade": False},
                 headers=como(g1)).json()["item"]
    assert p["so_necessidade"] is True
    v = cli.post("/brasil/itens", json={"nome": "Barco", "grupo": "energia_mobilidade", "unidade": "veículos", "so_necessidade": True},
                 headers=como(g1)).json()["item"]
    c = cli.post("/brasil/itens", json={"nome": "Querosene", "grupo": "energia_mobilidade", "unidade": "litros"}, headers=como(g1)).json()["item"]
    s = cli.post("/brasil/itens", json={"nome": "Lonas", "grupo": "estrutura_ativos", "unidade": "unidades", "so_necessidade": True},
                 headers=como(g1)).json()["item"]
    assert (v["so_necessidade"], c["so_necessidade"], s["so_necessidade"]) == (True, False, False)


@pytest.mark.parametrize("corpo", [
    {"nome": "X", "grupo": "sustento", "unidade": "kg"},
    {"nome": "Sabão", "grupo": "limpeza", "unidade": "kg"},
    {"nome": "Sabão", "grupo": "sustento", "unidade": ""},
    {"nome": "!!", "grupo": "sustento", "unidade": "kg"},
])
def test_item_novo_invalido_422(abrigo, corpo):
    cli, _, g1, *_ = abrigo
    assert cli.post("/brasil/itens", json=corpo, headers=como(g1)).status_code == 422


def test_agua_minuscula_e_sinalizada_como_duplicado_sem_bloquear(abrigo):
    cli, _, g1, *_ = abrigo
    cli.post("/brasil/itens", json={"nome": "Água mineral", "grupo": "sustento", "unidade": "garrafas"}, headers=como(g1))
    sug = cli.get("/brasil/itens/sugestoes", params={"q": "agua"}, headers=como(g1)).json()
    assert [i["nome"] for i in sug["possiveis_duplicados"]] == ["Água", "Água mineral"]
    # criar mesmo assim é permitido: o agente só sinaliza, nunca une nem renomeia
    r = cli.post("/brasil/itens", json={"nome": "Agua potavel", "grupo": "sustento", "unidade": "litros"}, headers=como(g1)).json()
    assert r["existente"] is False and r["item"]["nome"] == "Agua potavel"
    assert "Água" in {i["nome"] for i in r["possiveis_duplicados"]}
    sem = cli.post("/brasil/itens", json={"nome": "Lanternas", "grupo": "estrutura_ativos", "unidade": "unidades"}, headers=como(g1)).json()
    assert sem["possiveis_duplicados"] == []


def test_regra_de_duplicados():
    itens = [{"id": 1, "nome": "Água"}, {"id": 2, "nome": "Água mineral"}, {"id": 3, "nome": "Gasolina"},
             {"id": 4, "nome": "Diesel"}, {"id": 5, "nome": "Colchões"}, {"id": 6, "nome": "Equipe de saúde"}]
    nomes = lambda n: [i["nome"] for i in duplicados(n, itens)]
    assert nomes("agua") == ["Água", "Água mineral"]       # igual primeiro, depois o que contém
    assert nomes("ÁGUAS!") == ["Água", "Água mineral"]
    assert nomes("Colchão") == ["Colchões"]                 # plural
    assert nomes("Gasolina comum") == ["Gasolina"]
    assert nomes("Gazolina") == ["Gasolina"]                # erro de digitação (difflib)
    assert nomes("saúde") == ["Equipe de saúde"]
    assert nomes("Diesel") == ["Diesel"] and "Gasolina" not in nomes("Diesel")
    assert nomes("Cobertores") == [] and nomes("") == [] and nomes("de") == []


def test_agente_roda_no_local_e_os_outros_provedores_caem_para_o_local(api, monkeypatch):
    from middleware.brasil.orquestracao.claude import ClaudeProvedor
    from middleware.brasil.orquestracao.watsonx import WatsonxProvedor
    _, rotas = api
    ctx = {"itens": [{"id": 1, "nome": "Água"}, {"id": 2, "nome": "Diesel"}]}
    r = orquestracao.executar(rotas.CFG, "itens_duplicados", "agua", ctx)
    assert r.provedor == "local" and [i["id"] for i in r.dados] == [1] and "Água" in r.texto
    monkeypatch.setenv("WO_API_KEY", "x")
    monkeypatch.setenv("WO_INSTANCE", "x")
    r = orquestracao.executar(rotas.CFG, "itens_duplicados", "agua", ctx, provedor=WatsonxProvedor(rotas.CFG, chamar=lambda *a, **k: 1 / 0))
    assert r.provedor == "local" and [i["id"] for i in r.dados] == [1] and "sem agente itens_duplicados" in r.avisos[0]

    class SemChamar:
        def __getattr__(self, nome):
            raise AssertionError("não devia chamar a Claude API")
    r = orquestracao.executar(rotas.CFG, "itens_duplicados", "agua", ctx, provedor=ClaudeProvedor(rotas.CFG, cliente=SemChamar()))
    assert r.provedor == "local" and [i["id"] for i in r.dados] == [1]


def test_gestor_nao_ve_nem_mexe_no_estoque_de_outro_abrigo(abrigo):
    cli, _, g1, g2, aid = abrigo
    agua = item(cli, g1, "Água")
    cli.put(f"/brasil/abrigos/{aid}/estoque/{agua['id']}", json={"status": "precisa", "quantidade": 10}, headers=como(g1))
    assert cli.get(f"/brasil/abrigos/{aid}/estoque", headers=como(g2)).status_code == 404
    assert cli.put(f"/brasil/abrigos/{aid}/estoque/{agua['id']}", json={"status": "ok"}, headers=como(g2)).status_code == 404
    assert cli.delete(f"/brasil/abrigos/{aid}/estoque/{agua['id']}", headers=como(g2)).status_code == 404
    assert cli.get(f"/brasil/abrigos/{aid}/estoque", headers=como(g1)).json()[0]["status"] == "precisa"


@pytest.mark.parametrize("perfil", ["voluntario", "ong", "admin"])
def test_outros_perfis_recebem_403_no_estoque(abrigo, perfil):
    cli, _, g1, _, aid = abrigo
    agua = item(cli, g1, "Água")
    h = como(cli.post(f"/brasil/dev/usuario/{perfil}").json()["id"])
    assert cli.get("/brasil/itens/grupos", headers=h).status_code == 403
    assert cli.get("/brasil/itens/sugestoes", params={"q": "agua"}, headers=h).status_code == 403
    assert cli.post("/brasil/itens", json={"nome": "Sabão", "grupo": "sustento", "unidade": "kg"}, headers=h).status_code == 403
    assert cli.get(f"/brasil/abrigos/{aid}/estoque", headers=h).status_code == 403
    assert cli.put(f"/brasil/abrigos/{aid}/estoque/{agua['id']}", json={"status": "ok"}, headers=h).status_code == 403
    assert cli.delete(f"/brasil/abrigos/{aid}/estoque/{agua['id']}", headers=h).status_code == 403
    assert cli.get("/brasil/itens/sugestoes", params={"q": "agua"}).status_code == 401
