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


# AC-012.1
def test_ac_012_1_criar_campanha_usa_a_ong_da_sessao(front, logar):
    cli, api = front
    logar(cli, "org", uid=3)
    api.respostas[("POST", "/campanhas")] = (200, {"id": 9})
    r = cli.post("/brasil/api/campanhas", json={"org_id": 999, "title": "Apoio", "crisis_id": "cemaden-1"})
    assert r.get_json()["id"] == 9 and api.chamadas[-1][2]["org_id"] == 3


def test_fr012_campanha_de_outra_ong_da_404(front, logar):
    cli, api = front
    logar(cli, "org", uid=3)
    api.respostas[("GET", "/campanhas/5")] = (200, {"id": 5, "org_id": 4, "crisis_id": "x"})
    assert cli.get("/brasil/ong/campanhas/5").status_code == 404


# AC-011.1
def test_ac_011_1_resposta_ao_convite_usa_o_voluntario_da_sessao(front, logar):
    cli, api = front
    logar(cli, "volunteer", uid=7)
    api.respostas[("PUT", "/convites/12")] = (200, {"ok": True, "status": "confirmed"})
    assert cli.put("/brasil/api/convites/12", json={"status": "confirmed", "user_id": 1}).status_code == 200
    assert api.chamadas[-1] == ("PUT", "/convites/12", {"user_id": 7, "status": "confirmed"})


# AC-014.1
def test_ac_014_1_painel_da_ong_mostra_os_numeros(front, logar):
    cli, api = front
    logar(cli, "org", uid=3)
    api.respostas[("GET", "/ong/3/painel")] = (200, {"voluntarios_selecionados": 8, "campanhas_ativas": 2, "crises_apoiadas": 2,
        "habilidades": {"resgate": 7}, "crescimento": {"1": [{"dia": "2026-10-16", "n": 3}]},
        "campanhas": [{"id": 1, "title": "Apoio POA", "status": "active", "crisis_title": "Chuva", "crisis_uf": "RS",
                       "urgency": "alta", "selecionados": 3, "target_volunteers": 10}]})
    api.respostas[("GET", "/crises")] = (200, [])
    html = cli.get("/brasil/ong").get_data(as_text=True)
    assert "<b>8</b>" in html and "<b>2</b>" in html and "resgate" in html and "Apoio POA" in html


# AC-030.1
def test_ac_030_1_chat_usa_o_usuario_da_sessao(front, logar):
    cli, api = front
    logar(cli, "volunteer", uid=7)
    api.respostas[("POST", "/chat")] = (200, {"texto": "Encontrei 2 crises", "dados": {}, "provedor": "local", "avisos": []})
    r = cli.post("/brasil/api/chat", json={"mensagem": "onde posso ajudar?", "user_id": 1})
    assert r.get_json()["texto"] == "Encontrei 2 crises"
    assert api.chamadas[-1][2] == {"user_id": 7, "mensagem": "onde posso ajudar?", "crisis_id": None}


# AC-025.1
def test_ac_025_1_so_admin_confirma_noticia(front, logar):
    cli, api = front
    logar(cli, "org", uid=3)
    assert cli.put("/brasil/api/crises/noticia-1/verificacao", json={"acao": "confirmar"}).status_code == 403
    logar(cli, "admin", uid=1)
    api.respostas[("PUT", "/crises/noticia-1/verificacao")] = (200, {"id": "noticia-1", "verificacao": "verificada"})
    assert cli.put("/brasil/api/crises/noticia-1/verificacao", json={"acao": "confirmar"}).get_json()["verificacao"] == "verificada"
    assert api.chamadas[-1][2]["user_id"] == 1


# AC-034.1
def test_ac_034_1_pagina_de_previsoes(front, logar):
    cli, api = front
    logar(cli, "volunteer")
    api.respostas[("GET", "/previsoes")] = (200, {"texto": "1 município", "provedor": "local", "avisos": [], "dados": [
        {"municipio": "Altamira", "uf": "PA", "tipo": "wildfire", "dias_com_crise": 4, "severidade_max": 4,
         "probabilidade": "baixa", "acao": "Preparar resposta"}]})
    html = cli.get("/brasil/previsoes").get_data(as_text=True)
    assert "Altamira – PA" in html and "Previsões de risco" in html


# AC-035.1
def test_ac_035_1_notificar_so_ong_ou_admin(front, logar):
    cli, api = front
    logar(cli, "volunteer")
    assert cli.post("/brasil/api/crises/x/notificar").status_code == 403
    logar(cli, "org", uid=3)
    api.respostas[("POST", "/crises/x/notificar")] = (200, {"modo": "fila", "enfileiradas": 3})
    assert cli.post("/brasil/api/crises/x/notificar", json={"limite": 3}).get_json()["enfileiradas"] == 3
