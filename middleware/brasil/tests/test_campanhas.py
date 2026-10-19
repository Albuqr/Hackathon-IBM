"""FR-011–FR-014 e FR-016 pela API /brasil."""
import threading

from middleware.brasil import ingestao


def como(uid) -> dict:
    """Cabeçalho de identidade que o encaminhador do frontend manda (ADR 0004)."""
    return {"X-Brasil-Usuario": str(uid)}


def ev(id_, lat, lon, sev=3):
    return {"id": id_, "title": id_, "lat": lat, "lon": lon, "severity": sev, "crisis_type": "meteorological", "source": "cemaden"}


def preparar(cli, rotas, n_vol=0):
    ingestao.executar(rotas.CFG, fontes={"cemaden": lambda: [ev("cemaden-sb", -28.75, -55.8, 4), ev("cemaden-poa", -30.03, -51.22)]})
    ong = cli.post("/brasil/dev/usuario/ong").json()["id"]
    vol = cli.post("/brasil/dev/usuario/voluntario").json()["id"]
    extras = []
    import sqlite3
    conn = sqlite3.connect(rotas.CFG.db_path)
    for i in range(n_vol):
        cur = conn.execute("INSERT INTO users (email, password_hash, role, name, skills, lat, lon) VALUES (?,?,?,?,?,?,?)",
                           (f"v{i}@t.br", "x", "volunteer", f"V{i}", '["resgate"]', -29.0 - i / 10, -51.0))
        extras.append(cur.lastrowid)
    conn.commit(); conn.close()
    return ong, vol, extras


def campanha(cli, ong, **kw):
    corpo = {"title": "Apoio em São Borja", "crisis_id": "cemaden-sb", "target_volunteers": 10,
             "skills_needed": ["logística"], "urgency": "alta"} | kw
    return cli.post("/brasil/campanhas", json=corpo, headers=como(ong))


# AC-012.1
def test_ac_012_1_ong_cria_campanha_para_crise_br(api):
    cli, rotas = api
    ong, _, _ = preparar(cli, rotas)
    r = campanha(cli, ong)
    assert r.status_code == 200
    c = r.json()
    assert c["status"] == "active" and c["crisis_title"] == "cemaden-sb" and c["target_volunteers"] == 10
    assert [x["id"] for x in cli.get(f"/brasil/campanhas?org_id={ong}", headers=como(ong)).json()] == [c["id"]]


def test_fr012_crise_inexistente_e_voluntario_nao_cria_e_ong_so_edita_a_sua(api):
    cli, rotas = api
    ong, vol, _ = preparar(cli, rotas)
    assert campanha(cli, ong, crisis_id="nao-existe").status_code == 422
    assert campanha(cli, vol).status_code == 403
    cid = campanha(cli, ong).json()["id"]
    assert cli.put(f"/brasil/campanhas/{cid}", json={"title": "X invadido"}, headers=como(vol)).status_code == 403
    r = cli.put(f"/brasil/campanhas/{cid}", json={"status": "closed", "target_volunteers": 5}, headers=como(ong))
    assert r.json()["status"] == "closed" and r.json()["target_volunteers"] == 5


# AC-013.1
def test_ac_013_1_adicionar_voluntario_gera_convite_pendente(api):
    cli, rotas = api
    ong, vol, _ = preparar(cli, rotas)
    cid = campanha(cli, ong).json()["id"]
    disp = cli.get("/brasil/voluntarios/disponiveis", params={"crisis_id": "cemaden-sb"}, headers=como(ong)).json()
    assert vol in [d["id"] for d in disp] and disp[0]["distancia_km"] is not None
    assert cli.post(f"/brasil/campanhas/{cid}/voluntarios", json={"volunteer_id": vol}, headers=como(ong)).json()["ok"]
    [na_campanha] = cli.get(f"/brasil/campanhas/{cid}/voluntarios", headers=como(ong)).json()
    assert na_campanha["volunteer_id"] == vol and na_campanha["status"] == "selected"
    [convite] = cli.get(f"/brasil/voluntario/{vol}/campanhas", headers=como(vol)).json()
    assert convite["status"] == "selected" and convite["org_name"] == "ONG Brasil Solidário"
    assert cli.delete(f"/brasil/campanhas/{cid}/voluntarios/{vol}", headers=como(ong)).json()["ok"]
    assert cli.get(f"/brasil/campanhas/{cid}/voluntarios", headers=como(ong)).json() == []


# AC-011.1
def test_ac_011_1_voluntario_aceita_convite_e_ong_ve(api):
    cli, rotas = api
    ong, vol, extras = preparar(cli, rotas, n_vol=1)
    cid = campanha(cli, ong).json()["id"]
    cli.post(f"/brasil/campanhas/{cid}/voluntarios", json={"volunteer_id": vol}, headers=como(ong))
    [convite] = cli.get(f"/brasil/voluntario/{vol}/campanhas", headers=como(vol)).json()
    assert cli.put(f"/brasil/convites/{convite['cv_id']}", json={"status": "confirmed"}, headers=como(extras[0])).status_code == 403
    assert cli.put(f"/brasil/convites/{convite['cv_id']}", json={"status": "confirmed"}, headers=como(vol)).json()["status"] == "confirmed"
    assert cli.get(f"/brasil/campanhas/{cid}/voluntarios", headers=como(ong)).json()[0]["status"] == "confirmed"
    assert cli.get(f"/brasil/campanhas/{cid}", headers=como(ong)).json()["confirmados"] == 1


# AC-014.1
def test_ac_014_1_painel_da_ong_soma_voluntarios_e_habilidades(api):
    cli, rotas = api
    ong, vol, extras = preparar(cli, rotas, n_vol=7)
    c1 = campanha(cli, ong).json()["id"]
    c2 = campanha(cli, ong, title="Apoio POA", crisis_id="cemaden-poa").json()["id"]
    for v in [vol] + extras[:2]:
        cli.post(f"/brasil/campanhas/{c1}/voluntarios", json={"volunteer_id": v}, headers=como(ong))
    for v in extras[2:7]:
        cli.post(f"/brasil/campanhas/{c2}/voluntarios", json={"volunteer_id": v}, headers=como(ong))
    p = cli.get(f"/brasil/ong/{ong}/painel", headers=como(ong)).json()
    assert p["voluntarios_selecionados"] == 8 and p["campanhas_ativas"] == 2 and p["crises_apoiadas"] == 2
    assert p["habilidades"]["resgate"] == 7 and p["habilidades"]["primeiros socorros"] == 1
    assert sum(d["n"] for d in p["crescimento"][str(c2)]) == 5


# AC-016.1
def test_ac_016_1_ingestao_automatica_roda_uma_vez_em_61_min(api, monkeypatch):
    from middleware.brasil.config import carregar
    monkeypatch.setenv("BRASIL_INGESTAO_AUTO_MIN", "60")
    cfg = carregar()
    relogio = {"t": 0}
    chamadas = []

    def esperar(segundos):  # relógio simulado: o serviço fica de pé por 61 min
        relogio["t"] += segundos
        return relogio["t"] > 61 * 60

    ingestao.laco_automatico(cfg, threading.Event(), executar_fn=lambda c: chamadas.append(relogio["t"]) or {}, esperar=esperar)
    assert chamadas == [3600]


def test_fr016_desligada_nao_cria_thread(api):
    _, rotas = api
    assert rotas.CFG.ingestao_auto_min == 0 and ingestao.iniciar_automatico(rotas.CFG) is None


# AC-017.1 (brasil-app): números do painel são da própria ONG
def test_ac_017_1_painel_conta_voluntarios_da_ong(api):
    cli, rotas = api
    ong, vol, extras = preparar(cli, rotas, n_vol=4)
    c1 = campanha(cli, ong).json()["id"]
    c2 = campanha(cli, ong, title="Apoio POA", crisis_id="cemaden-poa").json()["id"]
    for v in (vol, extras[0]):
        cli.post(f"/brasil/campanhas/{c1}/voluntarios", json={"volunteer_id": v}, headers=como(ong))
    cli.post(f"/brasil/campanhas/{c2}/voluntarios", json={"volunteer_id": extras[1]}, headers=como(ong))
    import sqlite3
    conn = sqlite3.connect(rotas.CFG.db_path)
    conn.execute("UPDATE users SET available=0 WHERE id IN (?, ?)", (vol, extras[0]))
    conn.commit(); conn.close()
    p = cli.get(f"/brasil/ong/{ong}/painel", headers=como(ong)).json()
    # 3 voluntários nas campanhas (extras[2] e [3] existem, disponíveis, mas não são da ONG)
    assert (p["campanhas_ativas"], p["voluntarios"], p["voluntarios_disponiveis"]) == (2, 3, 1)
