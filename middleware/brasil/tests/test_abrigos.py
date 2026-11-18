"""Gestor de abrigo e abrigos (ADR 0005), pela API /brasil."""
import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.brasil import db
from middleware.brasil.abrigos import abrigo_do_gestor, gestor_verificado

POA = {"lat": -30.0346, "lon": -51.2177}  # Porto Alegre, 4314902


def como(uid) -> dict:
    return {"X-Brasil-Usuario": str(uid)}


def novo(**kw) -> dict:
    return {"nome": "Abrigo Ginásio Fictício", "endereco": "Rua de Teste, 100", **POA, "capacidade": 120,
            "tipo": "temporario", "ativo": True, "sensivel": False, **kw}


@pytest.fixture
def gestores(api):
    cli, rotas = api
    g1 = cli.post("/brasil/dev/usuario/gestor").json()["id"]
    g2 = cli.post("/brasil/dev/usuario/gestor2").json()["id"]
    return cli, rotas, g1, g2


def crise(rotas, id_="cemaden-poa"):
    conn = db.conectar(rotas.CFG)
    conn.execute("INSERT INTO crises (id, title, country, lat, lon, severity, uf) VALUES (?,?,?,?,?,?,?)",
                 (id_, "Chuva fictícia POA", "Brasil", -30.03, -51.22, 3, "RS"))
    conn.commit()
    conn.close()


def test_cadastro_cria_so_gestor_de_abrigo_e_email_repetido_409(api):
    cli, rotas = api
    r = cli.post("/brasil/cadastro", json={"name": "Maria Fictícia", "email": " Maria@Teste.Brasil ", "phone": "51 99999-0000",
                                           "senha": "senha-forte-1", "role": "admin"})
    assert r.status_code == 200
    u = r.json()
    assert u["role"] == "gestor_abrigo" and u["email"] == "maria@teste.brasil" and u["phone"] == "51 99999-0000"
    assert "password_hash" not in u and u["link_code"] is None
    conn = db.conectar(rotas.CFG)
    assert conn.execute("SELECT password_hash FROM users WHERE id=?", (u["id"],)).fetchone()[0] == rotas._hash("senha-forte-1")
    conn.close()
    assert cli.post("/brasil/login", json={"email": "maria@teste.brasil", "senha": "senha-forte-1"}).json()["id"] == u["id"]
    dup = cli.post("/brasil/cadastro", json={"name": "Outra", "email": "MARIA@teste.brasil", "senha": "outra-senha-2"})
    assert dup.status_code == 409
    # já pode criar abrigo
    assert cli.post("/brasil/abrigos", json=novo(), headers=como(u["id"])).status_code == 200


@pytest.mark.parametrize("corpo", [
    {"name": "Maria", "email": "m@teste.brasil", "senha": "curta"},
    {"name": "Maria", "email": "sem-arroba", "senha": "senha-forte-1"},
    {"name": "", "email": "m@teste.brasil", "senha": "senha-forte-1"},
])
def test_cadastro_invalido_422(api, corpo):
    cli, _ = api
    assert cli.post("/brasil/cadastro", json=corpo).status_code == 422


def test_cria_abrigo_nao_verificado_com_municipio_e_uf(gestores):
    cli, _, g1, _ = gestores
    r = cli.post("/brasil/abrigos", json=novo(), headers=como(g1))
    assert r.status_code == 200
    a = r.json()
    assert (a["municipio_ibge"], a["uf"], a["municipio"]) == (4314902, "RS", "Porto Alegre")
    assert a["verificado"] is False and a["ativo"] is True and a["sensivel"] is False
    assert a["gestor_id"] == g1 and a["capacidade"] == 120 and a["crises"] == []
    assert [x["id"] for x in cli.get("/brasil/abrigos", headers=como(g1)).json()] == [a["id"]]


def test_municipio_do_ponto_e_fora_do_brasil_422(gestores):
    cli, _, g1, _ = gestores
    assert cli.get("/brasil/abrigos/municipio", params=POA, headers=como(g1)).json()["uf"] == "RS"
    fora = {"lat": -34.9, "lon": -56.16}  # Montevidéu
    assert cli.get("/brasil/abrigos/municipio", params=fora, headers=como(g1)).status_code == 422
    assert cli.post("/brasil/abrigos", json=novo(**fora), headers=como(g1)).status_code == 422
    assert cli.get("/brasil/abrigos", headers=como(g1)).json() == []


@pytest.mark.parametrize("campo,valor", [("capacidade", 0), ("capacidade", -3), ("tipo", "hotel"), ("nome", "")])
def test_campos_invalidos_422(gestores, campo, valor):
    cli, _, g1, _ = gestores
    assert cli.post("/brasil/abrigos", json=novo(**{campo: valor}), headers=como(g1)).status_code == 422


def test_vinculo_com_crise_existente_e_crise_inexistente_422(gestores):
    cli, rotas, g1, _ = gestores
    crise(rotas)
    assert cli.post("/brasil/abrigos", json=novo(crises=["nao-existe"]), headers=como(g1)).status_code == 422
    a = cli.post("/brasil/abrigos", json=novo(crises=["cemaden-poa", "cemaden-poa"]), headers=como(g1)).json()
    assert [c["id"] for c in a["crises"]] == ["cemaden-poa"]
    # editar sem "crises" mantém; com lista vazia remove
    e = cli.put(f"/brasil/abrigos/{a['id']}", json=novo(nome="Outro nome"), headers=como(g1)).json()
    assert e["nome"] == "Outro nome" and [c["id"] for c in e["crises"]] == ["cemaden-poa"]
    assert cli.put(f"/brasil/abrigos/{a['id']}", json=novo(crises=[]), headers=como(g1)).json()["crises"] == []


def test_um_gestor_nao_ve_nem_edita_o_abrigo_do_outro(gestores):
    cli, _, g1, g2 = gestores
    a = cli.post("/brasil/abrigos", json=novo(), headers=como(g1)).json()
    assert cli.get(f"/brasil/abrigos/{a['id']}", headers=como(g2)).status_code == 404
    assert cli.put(f"/brasil/abrigos/{a['id']}", json=novo(nome="Tomado"), headers=como(g2)).status_code == 404
    assert cli.post(f"/brasil/dev/abrigos/{a['id']}/verificar", headers=como(g2)).status_code == 404
    assert cli.get("/brasil/abrigos", headers=como(g2)).json() == []
    assert cli.get(f"/brasil/abrigos/{a['id']}", headers=como(g1)).json()["nome"] == "Abrigo Ginásio Fictício"


@pytest.mark.parametrize("perfil", ["voluntario", "ong", "admin"])
def test_outros_perfis_recebem_403_nas_rotas_de_abrigo(gestores, perfil):
    cli, _, g1, _ = gestores
    a = cli.post("/brasil/abrigos", json=novo(), headers=como(g1)).json()
    uid = cli.post(f"/brasil/dev/usuario/{perfil}").json()["id"]
    h = como(uid)
    assert cli.get("/brasil/abrigos", headers=h).status_code == 403
    assert cli.post("/brasil/abrigos", json=novo(), headers=h).status_code == 403
    assert cli.get(f"/brasil/abrigos/{a['id']}", headers=h).status_code == 403
    assert cli.put(f"/brasil/abrigos/{a['id']}", json=novo(), headers=h).status_code == 403
    assert cli.get("/brasil/abrigos/municipio", params=POA, headers=h).status_code == 403
    assert cli.post(f"/brasil/dev/abrigos/{a['id']}/verificar", headers=h).status_code == 404
    assert cli.get("/brasil/abrigos").status_code == 401


def test_verificacao_de_teste_alterna_e_edicao_nao_muda_verificado(gestores):
    cli, rotas, g1, _ = gestores
    a = cli.post("/brasil/abrigos", json=novo(), headers=como(g1)).json()
    v = cli.post(f"/brasil/dev/abrigos/{a['id']}/verificar", headers=como(g1)).json()
    assert v["verificado"] is True and v["verificado_em"]
    assert cli.put(f"/brasil/abrigos/{a['id']}", json={**novo(), "verificado": False}, headers=como(g1)).json()["verificado"] is True
    conn = db.conectar(rotas.CFG)
    assert gestor_verificado(conn, g1) is True
    conn.close()
    v = cli.post(f"/brasil/dev/abrigos/{a['id']}/verificar", headers=como(g1)).json()
    assert v["verificado"] is False and v["verificado_em"] is None


def test_verificacao_de_teste_responde_404_sem_login_de_teste(gestores, monkeypatch):
    cli, rotas, g1, _ = gestores
    a = cli.post("/brasil/abrigos", json=novo(), headers=como(g1)).json()
    monkeypatch.delenv("BRASIL_DEV_LOGIN")
    importlib.reload(rotas)
    app = FastAPI()
    app.include_router(rotas.router)
    prod = TestClient(app)
    assert prod.post(f"/brasil/dev/abrigos/{a['id']}/verificar", headers=como(g1)).status_code == 404
    assert prod.post(f"/brasil/dev/abrigos/{a['id']}/verificar").status_code == 404  # nem pede login
    assert prod.get(f"/brasil/abrigos/{a['id']}", headers=como(g1)).json()["verificado"] is False


def test_helpers_para_abrigados_e_estoque(gestores):
    cli, rotas, g1, g2 = gestores
    a = cli.post("/brasil/abrigos", json=novo(), headers=como(g1)).json()
    conn = db.conectar(rotas.CFG)
    try:
        assert abrigo_do_gestor(conn, a["id"], {"id": g1, "role": "gestor_abrigo"})["nome"] == a["nome"]
        with pytest.raises(Exception) as e:
            abrigo_do_gestor(conn, a["id"], {"id": g2, "role": "gestor_abrigo"})
        assert e.value.status_code == 404
        assert gestor_verificado(conn, g1) is False and gestor_verificado(conn, g2) is False
    finally:
        conn.close()
