"""brasil-app: filtros de /brasil/crises (FR-022, FR-009) e identidade encaminhada (FR-024)."""
from middleware.brasil import ingestao

FLORIANOPOLIS, TORRES, PORTO_ALEGRE = 4205407, 4321501, 4314902


def como(uid) -> dict:
    """Cabeçalho de identidade que o encaminhador do frontend manda (ADR 0004)."""
    return {"X-Brasil-Usuario": str(uid)}


def semear(rotas):
    ingestao.executar(rotas.CFG, fontes={
        "inmet": lambda: [{"id": "inmet-aviso", "title": "Chuvas intensas", "lat": -27.59, "lon": -48.55, "severity": 3,
                           "crisis_type": "meteorological", "source": "inmet",
                           "municipios_afetados": [FLORIANOPOLIS, TORRES]}],
        "inpe": lambda: [{"id": "inpe-poa", "title": "Focos em Porto Alegre", "lat": -30.03, "lon": -51.22,
                          "severity": 2, "crisis_type": "wildfire", "source": "inpe"}],
    })


# AC-022.1 (brasil-app) e AC-009.1: UF pela área, não pelo centro
def test_ac_022_1_filtros_da_api_com_uf_pela_area(api):
    cli, rotas = api
    semear(rotas)
    assert [c["id"] for c in cli.get("/brasil/crises", params={"uf": "RS", "sev_min": 3}).json()] == ["inmet-aviso"]
    assert {c["id"] for c in cli.get("/brasil/crises", params={"uf": "RS"}).json()} == {"inmet-aviso", "inpe-poa"}
    assert [c["id"] for c in cli.get("/brasil/crises", params={"uf": "SC"}).json()] == ["inmet-aviso"]
    assert [c["id"] for c in cli.get("/brasil/crises", params={"tipo": "wildfire"}).json()] == ["inpe-poa"]
    assert [c["id"] for c in cli.get("/brasil/crises", params={"q": "porto alegre"}).json()] == ["inpe-poa"]
    assert len(cli.get("/brasil/crises", params={"limite": 1}).json()) == 1


def test_associados_separados_em_voluntarios_e_ongs(api):
    cli, rotas = api
    semear(rotas)
    vol = cli.post("/brasil/dev/usuario/voluntario").json()["id"]
    ong = cli.post("/brasil/dev/usuario/ong").json()["id"]
    cli.post("/brasil/crises/inpe-poa/inscrever", headers=como(vol))
    r = cli.post("/brasil/crises/inpe-poa/inscrever", headers=como(ong)).json()
    assert (r["inscritos"], r["voluntarios"], r["ongs"]) == (2, 1, 1)
    [c] = [x for x in cli.get("/brasil/crises").json() if x["id"] == "inpe-poa"]
    assert (c["voluntarios"], c["ongs"]) == (1, 1)


# AC-024.1
def test_ac_024_1_papel_vem_do_banco_nao_do_corpo(api):
    cli, rotas = api
    semear(rotas)
    vol = cli.post("/brasil/dev/usuario/voluntario").json()["id"]
    admin = cli.post("/brasil/dev/usuario/admin").json()["id"]
    url = "/brasil/crises/inpe-poa/verificacao"
    assert cli.put(url, json={"acao": "confirmar", "user_id": admin}, headers=como(vol)).status_code == 403
    assert cli.put(url, json={"acao": "confirmar"}).status_code == 401
    assert cli.put(url, json={"acao": "confirmar"}, headers=como(99999)).status_code == 401
    assert cli.get(f"/brasil/usuarios/{admin}", headers=como(vol)).status_code == 403
    assert cli.get("/brasil/distribuicao", headers=como(vol)).status_code == 403
    assert cli.post("/brasil/ingestao", headers=como(vol)).status_code == 403
