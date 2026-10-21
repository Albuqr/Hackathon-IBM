"""CSRF do frontend: token na sessão, campo oculto nos formulários, modos report/enforce/off."""
import os

import pytest

DADOS = {"email": "x@teste.brasil", "senha": "senha"}
ENTRAR = "/brasil/entrar"  # a API é simulada (conftest): sem credencial válida ela só devolve 404
RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LAYOUTS = ("templates/base.html", "templates/layout_base.html", "brasil/templates/brasil/base.html")
FORMULARIOS = ("templates/login.html", "templates/register.html", "templates/org_campaign_new.html",
               "brasil/templates/brasil/entrar.html")


def _token(cli):
    r = cli.get(ENTRAR)
    assert b'name="csrf_token"' in r.data
    with cli.session_transaction() as s:
        return s["_csrf"]


def test_formularios_e_layouts_levam_o_token():
    for caminho in FORMULARIOS:
        assert "{% csrf_token %}" in open(os.path.join(RAIZ, caminho), encoding="utf-8").read(), caminho
    for caminho in LAYOUTS:
        html = open(os.path.join(RAIZ, caminho), encoding="utf-8").read()
        assert 'name="csrf-token"' in html and "csrf.js" in html, caminho


def test_paginas_de_formulario_mostram_o_campo_oculto_com_o_token_da_sessao(front):
    cli, _ = front
    for caminho in ("/login", "/register", ENTRAR):
        r = cli.get(caminho)
        assert r.status_code == 200
        with cli.session_transaction() as s:
            assert f'name="csrf_token" value="{s["_csrf"]}"'.encode() in r.data, caminho


def test_modo_padrao_report_nao_bloqueia_e_registra_o_aviso(front, monkeypatch, caplog):
    monkeypatch.delenv("CSRF_MODE", raising=False)
    cli, _ = front
    with caplog.at_level("WARNING", logger="crisis.csrf"):
        r = cli.post(ENTRAR, data=DADOS)
    assert r.status_code == 200  # a página volta com o erro de credencial; nada foi barrado
    assert "CSRF: verificação falhou em POST /brasil/entrar (modo report)" in caplog.text


def test_enforce_bloqueia_sem_token_ou_com_token_errado(front, monkeypatch):
    monkeypatch.setenv("CSRF_MODE", "enforce")
    cli, _ = front
    assert cli.post(ENTRAR, data=DADOS).status_code == 400
    _token(cli)
    assert cli.post(ENTRAR, data={**DADOS, "csrf_token": "errado"}).status_code == 400
    assert cli.post(ENTRAR, data=DADOS, headers={"X-CSRF-Token": "errado"}).status_code == 400


def test_enforce_aceita_o_token_no_campo_e_no_cabecalho(front, monkeypatch):
    monkeypatch.setenv("CSRF_MODE", "enforce")
    cli, _ = front
    token = _token(cli)
    assert cli.post(ENTRAR, data={**DADOS, "csrf_token": token}).status_code == 200
    assert cli.post(ENTRAR, data=DADOS, headers={"X-CSRF-Token": token}).status_code == 200


def test_enforce_vale_para_put_delete_e_json_e_o_token_libera_o_fetch(front, monkeypatch):
    monkeypatch.setenv("CSRF_MODE", "enforce")
    cli, _ = front
    for metodo, caminho in (("put", "/api/campaigns/1"), ("delete", "/api/campaigns/1/volunteers/2"),
                            ("post", "/api/ingest")):
        assert getattr(cli, metodo)(caminho, json={}).status_code == 400, (metodo, caminho)
    token = _token(cli)
    # uma rota do encaminhador responde 401 sem login: com o token chega nela em vez de ser barrada
    assert cli.post("/brasil/acao/crises", json={}).status_code == 400
    assert cli.post("/brasil/acao/crises", json={}, headers={"X-CSRF-Token": token}).status_code == 401


def test_get_e_static_nunca_sao_barrados(front, monkeypatch):
    monkeypatch.setenv("CSRF_MODE", "enforce")
    cli, _ = front
    assert cli.get(ENTRAR).status_code == 200
    assert cli.get("/static/csrf.js").status_code == 200


def test_modo_off_nao_confere(front, monkeypatch):
    monkeypatch.setenv("CSRF_MODE", "off")
    cli, _ = front
    assert cli.post(ENTRAR, data=DADOS).status_code == 200


@pytest.mark.parametrize("valor", ["", "x", "a" * 500, "ç"])
def test_token_com_lixo_nao_derruba_a_checagem(front, monkeypatch, valor):
    monkeypatch.setenv("CSRF_MODE", "enforce")
    cli, _ = front
    _token(cli)
    assert cli.post(ENTRAR, data={**DADOS, "csrf_token": valor}).status_code == 400
