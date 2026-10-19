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
        for papel in ("volunteer", "org", "admin"):
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
    assert cli.post("/brasil/acao/verificar", json={"corpo": {}}).status_code == 400


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
