"""FR-001, FR-005, FR-009, FR-010, FR-015, FR-036 pelo frontend /brasil (API simulada)."""
USUARIO = {"id": 3, "role": "org", "name": "ONG de Teste", "org_name": "ONG Brasil Solidário", "email": "ong@teste.brasil"}


# AC-001.1
def test_ac_001_1_rotas_do_crisis_continuam_e_brasil_existe(front):
    cli, _ = front
    regras = {r.rule for r in cli.application.url_map.iter_rules()}
    assert {"/map", "/login", "/org/dashboard", "/api/events"} <= regras
    assert {"/brasil/", "/brasil/mapa", "/brasil/dev-login/<perfil>"} <= regras
    assert cli.get("/login").status_code == 200


# AC-005.1
def test_ac_005_1_dev_login_entra_e_abre_o_mapa(front, monkeypatch):
    monkeypatch.setenv("BRASIL_DEV_LOGIN", "1")
    cli, api = front
    api.respostas[("POST", "/dev/usuario/ong")] = (200, USUARIO)
    r = cli.get("/brasil/dev-login/ong")
    assert r.status_code == 302 and r.headers["Location"].endswith("/brasil/mapa")
    with cli.session_transaction() as s:
        assert s["br_user_id"] == 3 and s["br_role"] == "org" and s["br_nome"] == "ONG Brasil Solidário"
        assert "user_id" not in s  # não mistura com a sessão do Crisis


# AC-005.2
def test_ac_005_2_dev_login_desligado_da_404(front, monkeypatch):
    monkeypatch.delenv("BRASIL_DEV_LOGIN", raising=False)
    cli, api = front
    assert cli.get("/brasil/dev-login/admin").status_code == 404
    assert api.chamadas == []


def test_fr005_tela_de_entrada_mostra_logins_de_teste_so_quando_ligado(front, monkeypatch):
    cli, _ = front
    monkeypatch.setenv("BRASIL_DEV_LOGIN", "1")
    assert "dev-login/voluntario" in cli.get("/brasil/entrar").get_data(as_text=True)
    monkeypatch.delenv("BRASIL_DEV_LOGIN")
    assert "dev-login" not in cli.get("/brasil/entrar").get_data(as_text=True)


def test_paginas_exigem_login_e_papel(front, logar):
    cli, _ = front
    assert cli.get("/brasil/mapa").headers["Location"].endswith("/brasil/entrar")
    logar(cli, "volunteer")
    assert cli.get("/brasil/admin").status_code == 403
    assert cli.post("/brasil/api/ingestao").status_code == 403


# AC-009.1
def test_ac_009_1_inscricao_usa_o_usuario_da_sessao(front, logar):
    cli, api = front
    logar(cli, "volunteer", uid=7)
    api.respostas[("POST", "/crises/inpe-1/inscrever")] = (200, {"ok": True, "inscritos": 1})
    r = cli.post("/brasil/api/crises/inpe-1/inscrever", json={"user_id": 999})
    assert r.status_code == 200 and r.get_json()["inscritos"] == 1
    assert api.chamadas[-1] == ("POST", "/crises/inpe-1/inscrever", {"user_id": 7})


# AC-010.1
def test_ac_010_1_erro_de_localizacao_chega_ao_navegador(front, logar):
    cli, api = front
    logar(cli, "volunteer")
    api.respostas[("PUT", "/usuarios/7")] = (422, {"detail": "A localização precisa estar no Brasil"})
    r = cli.put("/brasil/api/perfil", json={"lat": -34.6, "lon": -58.38})
    assert r.status_code == 422 and r.get_json()["detail"] == "A localização precisa estar no Brasil"


# AC-015.1
def test_ac_015_1_admin_dispara_ingestao(front, logar):
    cli, api = front
    logar(cli, "admin", uid=1)
    api.respostas[("POST", "/ingestao")] = (200, {"gravadas": 10, "segundos": 3.2, "fontes": {}})
    assert cli.post("/brasil/api/ingestao").get_json()["gravadas"] == 10
    assert "Atualizar dados" in cli.get("/brasil/admin").get_data(as_text=True)


# AC-036.1
def test_ac_036_1_paginas_em_portugues(front, monkeypatch, logar):
    cli, api = front
    monkeypatch.setenv("BRASIL_DEV_LOGIN", "1")
    entrar = cli.get("/brasil/entrar").get_data(as_text=True)
    assert 'lang="pt-BR"' in entrar and "Entrar no Dash Brasil" in entrar
    logar(cli, "volunteer")
    api.respostas[("GET", "/usuarios/7")] = (200, {"id": 7, "name": "V", "skills": [], "languages": [], "lat": -30, "lon": -51,
                                                  "radius_km": 300, "available": 1, "link_code": "AB12-CD34"})
    perfil = cli.get("/brasil/perfil").get_data(as_text=True)
    mapa = cli.get("/brasil/mapa").get_data(as_text=True)
    assert "Meu perfil" in perfil and "Habilidades" in perfil and "AB12-CD34" in perfil
    assert "Crises por município" in mapa and "Quero" not in mapa  # botões vêm do JS


def test_malha_js_vira_script_e_fica_em_cache(front, monkeypatch):
    cli, _ = front
    g = cli.application.view_functions["brasil.inicio"].__globals__
    g["_malha_cache"].clear()
    chamadas = []

    class R:
        content = b'{"geojson":{}}'
        def raise_for_status(self): pass

    monkeypatch.setattr(g["requests"], "get", lambda *a, **k: chamadas.append(a) or R())
    for _ in range(2):
        r = cli.get("/brasil/malha.js")
        assert r.get_data() == b'window.MALHA={"geojson":{}};'
    assert len(chamadas) == 1
