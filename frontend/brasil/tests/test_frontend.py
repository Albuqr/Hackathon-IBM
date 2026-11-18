"""Frontend /brasil com a API simulada: entrada, papéis e o encaminhador (FR-023, ADR 0004)."""
import pytest

USUARIO = {"id": 3, "role": "org", "name": "ONG de Teste", "org_name": "ONG Brasil Solidário", "email": "ong@teste.brasil"}


def test_rotas_do_crisis_continuam_e_brasil_existe(front):
    cli, _ = front
    regras = {r.rule for r in cli.application.url_map.iter_rules()}
    assert {"/map", "/login", "/org/dashboard", "/api/events"} <= regras
    assert {"/brasil/", "/brasil/mapa", "/brasil/acao/<nome>", "/brasil/ong/nova"} <= regras
    assert not [r for r in regras if r.startswith("/brasil/api/")]  # as rotas JSON rasas saíram
    assert cli.get("/login").status_code == 200


def test_dev_login_entra_e_abre_o_mapa(front, monkeypatch):
    monkeypatch.setenv("BRASIL_DEV_LOGIN", "1")
    cli, api = front
    api.respostas[("POST", "/dev/usuario/ong")] = (200, USUARIO)
    r = cli.get("/brasil/dev-login/ong")
    assert r.status_code == 302 and r.headers["Location"].endswith("/brasil/mapa")
    with cli.session_transaction() as s:
        assert s["br_user_id"] == 3 and s["br_role"] == "org" and s["br_nome"] == "ONG Brasil Solidário"
        assert "user_id" not in s  # não mistura com a sessão do Crisis


def test_dev_login_desligado_da_404(front, monkeypatch):
    monkeypatch.delenv("BRASIL_DEV_LOGIN", raising=False)
    cli, api = front
    assert cli.get("/brasil/dev-login/admin").status_code == 404
    assert api.chamadas == []


def test_paginas_exigem_login_e_papel(front, logar):
    cli, _ = front
    assert cli.get("/brasil/mapa").headers["Location"].endswith("/brasil/entrar")
    assert cli.post("/brasil/acao/crises", json={}).status_code == 401
    logar(cli, "volunteer")
    assert cli.get("/brasil/admin").status_code == 403
    assert cli.get("/brasil/ong/nova").status_code == 403


# AC-023.1 — cada linha da POLITICA: quem pode chega à API com a identidade da sessão; quem não pode recebe 403.
def _params(caminho):
    import re
    return {n: "x1" for n in re.findall(r"\{(\w+)\}", caminho) if n != "eu"}


def _casos():
    from importlib import import_module
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    pol = import_module("brasil.encaminhador").POLITICA
    for nome, regra in pol.items():
        for papel in ("volunteer", "org", "admin", "gestor_abrigo"):
            yield nome, regra, papel


@pytest.mark.parametrize("nome,regra,papel", list(_casos()), ids=lambda v: v if isinstance(v, str) else "")
def test_ac_023_1_politica_do_encaminhador(front, logar, nome, regra, papel):
    cli, api = front
    logar(cli, papel, uid=7)
    caminho = regra.caminho.replace("{eu}", "7")
    for k, v in _params(regra.caminho).items():
        caminho = caminho.replace("{" + k + "}", v)
    api.respostas[(regra.metodo, caminho)] = (200, {"ok": True})
    r = cli.post(f"/brasil/acao/{nome}", json={"p": _params(regra.caminho), "corpo": {"user_id": 999, "org_id": 999}})
    if papel in regra.papeis:
        assert r.status_code == 200
        metodo, chamado, usuario, corpo, _ = api.chamadas[-1]
        assert (metodo, chamado, usuario) == (regra.metodo, caminho, 7)
    else:
        assert r.status_code == 403 and api.chamadas == []


def test_acao_desconhecida_e_parametro_que_escapa_do_caminho(front, logar):
    cli, api = front
    logar(cli, "admin", uid=1)
    assert cli.post("/brasil/acao/apagar_tudo", json={}).status_code == 403
    api.respostas[("PUT", "/crises/")] = (200, {"ok": True})
    cli.post("/brasil/acao/verificar", json={"p": {"crisis_id": "../usuarios/1"}, "corpo": {"acao": "confirmar"}})
    assert api.chamadas[-1][1] == "/crises/..%2Fusuarios%2F1/verificacao"
    n = len(api.chamadas)
    assert cli.post("/brasil/acao/verificar", json={"corpo": {}}).status_code == 400
    assert cli.post("/brasil/acao/verificar", json={"p": {"crisis_id": ".."}}).status_code == 400
    assert cli.post("/brasil/acao/crises", json=[1]).status_code == 400
    assert cli.post("/brasil/acao/crises", json={"p": "x"}).status_code == 400
    assert len(api.chamadas) == n  # nada disso chega à API


def test_encaminhador_so_aceita_json_csrf(front, logar):
    cli, api = front
    logar(cli, "admin", uid=1)
    r = cli.post("/brasil/acao/atualizar_dados", data="x", content_type="text/plain")
    assert r.status_code == 415 and api.chamadas == []
    assert cli.application.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_consulta_e_corpo_sao_repassados(front, logar):
    cli, api = front
    logar(cli, "org", uid=3)
    api.respostas[("GET", "/crises")] = (200, [])
    cli.post("/brasil/acao/crises", json={"q": {"uf": "RS", "q": "porto"}})
    assert api.chamadas[-1][4] == {"uf": "RS", "q": "porto"}
    api.respostas[("POST", "/campanhas")] = (200, {"id": 9})
    cli.post("/brasil/acao/criar_campanha", json={"corpo": {"title": "Apoio", "crisis_id": "c1"}})
    assert api.chamadas[-1][3] == {"title": "Apoio", "crisis_id": "c1"} and api.chamadas[-1][2] == 3


def test_malha_js_vira_script_e_fica_em_cache(front):
    cli, api = front
    for _ in range(2):
        assert cli.get("/brasil/malha.js").get_data() == b'window.MALHA={"geojson":{}};'
    assert api.malha_pedidos == 1


def test_malha_indisponivel_responde_503_sem_cache(front):
    cli, api = front
    api.malha = None
    r = cli.get("/brasil/malha.js")
    assert r.status_code == 503 and r.get_data() == b"window.MALHA=null;"


def test_campanha_de_outra_ong_da_404(front, logar):
    cli, api = front
    logar(cli, "org", uid=3)
    api.respostas[("GET", "/campanhas/5")] = (403, {"detail": "Esta campanha é de outra ONG"})
    assert cli.get("/brasil/ong/campanhas/5").status_code == 404
    assert api.chamadas[-1][2] == 3  # a API recebeu a identidade da sessão


def test_chat_antigo_redireciona(front, logar):
    cli, _ = front
    logar(cli, "volunteer")
    assert cli.get("/brasil/chat").headers["Location"].endswith("/brasil/perfil")


@pytest.mark.parametrize("papel,url", [
    ("volunteer", "/brasil/mapa"), ("volunteer", "/brasil/perfil"), ("volunteer", "/brasil/campanhas"),
    ("org", "/brasil/mapa"), ("org", "/brasil/ong"), ("org", "/brasil/ong/nova"), ("org", "/brasil/ong/campanhas/5"),
    ("admin", "/brasil/mapa"), ("admin", "/brasil/admin"), ("admin", "/brasil/previsoes"),
])
def test_ac_014_1_paginas_renderizam_no_shell_com_o_menu_do_perfil(front, logar, papel, url):
    cli, api = front
    logar(cli, papel, uid=3)
    api.respostas[("GET", "/usuarios/3")] = (200, {"id": 3, "name": "Ana", "skills": ["resgate"], "lat": -30, "lon": -51, "radius_km": 100, "available": 1, "link_code": "AB12-CD34"})
    api.respostas[("GET", "/ong/3/painel")] = (200, {"campanhas": [], "habilidades": {}, "voluntarios_disponiveis": 4})
    api.respostas[("GET", "/campanhas/5")] = (200, {"id": 5, "org_id": 3, "title": "Apoio", "status": "active", "crisis_id": "c1", "skills_needed": [],
                                                    "target_volunteers": 10, "selecionados": 0, "confirmados": 0, "urgency": "media"})
    api.respostas[("GET", "/previsoes")] = (200, {"dados": [], "texto": "", "avisos": [], "provedor": "local"})
    html = cli.get(url).get_data(as_text=True)
    assert 'class="app' in html and "statusbar" in html and "cliente.js" in html
    assert ("Minhas campanhas" in html) == (papel == "volunteer")
    assert (">Nova campanha<" in html) == (papel == "org")
    assert ('href="/brasil/admin"' in html) == (papel == "admin")
    assert ('id="lateral"' in html) == url.endswith("/mapa")  # só o mapa tem barra lateral


def test_dev_login_de_gestor_de_abrigo(front, monkeypatch):
    monkeypatch.setenv("BRASIL_DEV_LOGIN", "1")
    cli, api = front
    api.respostas[("POST", "/dev/usuario/gestor2")] = (200, {"id": 9, "role": "gestor_abrigo", "name": "Gestor 2", "email": "gestor2@teste.brasil"})
    assert cli.get("/brasil/dev-login/gestor2").status_code == 302
    with cli.session_transaction() as s:
        assert s["br_role"] == "gestor_abrigo" and s["br_user_id"] == 9


# ── gestor de abrigo (ADR 0005) ──────────────────────────────────────
ABRIGO = {"id": 4, "gestor_id": 9, "nome": "Ginásio Fictício", "endereco": "Rua de Teste, 1", "lat": -30.03, "lon": -51.22,
          "municipio_ibge": 4314902, "municipio": "Porto Alegre", "uf": "RS", "capacidade": 120, "tipo": "temporario",
          "ativo": True, "sensivel": False, "verificado": False, "verificado_em": None, "crises": []}


def test_gestor_entra_e_cai_no_abrigo(front, monkeypatch, logar):
    monkeypatch.setenv("BRASIL_DEV_LOGIN", "1")
    cli, api = front
    api.respostas[("POST", "/dev/usuario/gestor")] = (200, {"id": 9, "role": "gestor_abrigo", "name": "Gestora", "email": "gestor@teste.brasil"})
    assert cli.get("/brasil/dev-login/gestor").headers["Location"].endswith("/brasil/abrigo")
    assert cli.get("/brasil/").headers["Location"].endswith("/brasil/abrigo")
    api.respostas[("POST", "/login")] = (200, {"id": 9, "role": "gestor_abrigo", "name": "Gestora", "email": "gestor@teste.brasil"})
    assert cli.post("/brasil/entrar", data={"email": "gestor@teste.brasil", "senha": "x"}).headers["Location"].endswith("/brasil/abrigo")


def test_abrigo_sem_abrigo_mostra_o_cadastro_em_etapas(front, logar):
    cli, api = front
    logar(cli, "gestor_abrigo", uid=9)
    api.respostas[("GET", "/abrigos")] = (200, [])
    html = cli.get("/brasil/abrigo").get_data(as_text=True)
    assert 'id="etapas"' in html and "abrigo.js" in html and "leaflet" not in html.lower()
    assert ">Meu abrigo<" in html and api.chamadas[-1][:3] == ("GET", "/abrigos", 9)


def test_abrigo_com_abrigos_mostra_o_painel_e_marca_nao_verificado(front, logar, monkeypatch):
    monkeypatch.delenv("BRASIL_DEV_LOGIN", raising=False)
    cli, api = front
    logar(cli, "gestor_abrigo", uid=9)
    api.respostas[("GET", "/abrigos")] = (200, [ABRIGO, {**ABRIGO, "id": 5, "nome": "Escola Fictícia", "verificado": True}])
    html = cli.get("/brasil/abrigo").get_data(as_text=True)
    assert 'id="etapas"' not in html and "Ginásio Fictício" in html and "Porto Alegre · RS" in html
    assert html.count(">Não verificado<") == 1 and html.count(">Verificado<") == 1
    assert 'href="/brasil/abrigo/4/pessoas"' in html and 'href="/brasil/abrigo/4/estoque"' in html
    assert 'href="/brasil/abrigo/4/editar"' in html and "Novo abrigo" in html
    assert "data-verificar" not in html  # botão de teste só com o login de teste
    monkeypatch.setenv("BRASIL_DEV_LOGIN", "1")
    assert 'data-verificar="4"' in cli.get("/brasil/abrigo").get_data(as_text=True)
    assert 'id="etapas"' in cli.get("/brasil/abrigo?novo=1").get_data(as_text=True)


def test_editar_abrigo_de_outro_gestor_da_404(front, logar):
    cli, api = front
    logar(cli, "gestor_abrigo", uid=9)
    api.respostas[("GET", "/abrigos/4")] = (200, ABRIGO)
    html = cli.get("/brasil/abrigo/4/editar").get_data(as_text=True)
    assert '"municipio_ibge": 4314902' in html and 'id="etapas"' in html  # o abrigo vai para as etapas já preenchidas
    assert cli.get("/brasil/abrigo/77/editar").status_code == 404  # a API respondeu 404


@pytest.mark.parametrize("papel", ["volunteer", "org", "admin"])
def test_paginas_do_abrigo_so_para_gestor(front, logar, papel):
    cli, api = front
    logar(cli, papel)
    assert cli.get("/brasil/abrigo").status_code == 403
    assert cli.get("/brasil/abrigo/4/editar").status_code == 403
    assert ">Meu abrigo<" not in cli.get("/brasil/mapa").get_data(as_text=True)
    assert api.chamadas == []


def test_abrigo_exige_login(front):
    cli, _ = front
    assert cli.get("/brasil/abrigo").headers["Location"].endswith("/brasil/entrar")
