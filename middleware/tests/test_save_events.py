"""Caracterização de /save_event e /save_events (comportamento atual, antes de gravar_eventos).

Sem rede e sem provedor: usa o TestClient e um SQLite temporário criado pelo init_db.py.
"""
import importlib
import os
import sqlite3
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class _Resp:
    def __init__(self, corpo):
        self._corpo = corpo

    def json(self):
        return self._corpo


@pytest.fixture
def api(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    subprocess.run([sys.executable, os.path.join(RAIZ, "init_db.py")], cwd=tmp_path, check=True, capture_output=True)
    caminho = tmp_path / "data" / "crisis.db"
    monkeypatch.setenv("DB_PATH", str(caminho))
    monkeypatch.setenv("BRASIL_DB_PATH", str(tmp_path / "brasil.db"))
    monkeypatch.delenv("SECRET_KEY", raising=False)  # API aberta: sem token nos testes
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    sys.path.insert(0, os.path.join(RAIZ, "tools"))
    import middleware.main as main
    main = importlib.reload(main)
    cli = TestClient(main.app)
    # O lote é chamado direto na função da rota: com o FastAPI instalado (0.165) a rota recusa o JSON
    # em lista (ver test_save_events_http_recusa_json_em_lista_hoje), então o HTTP não alcança o código.
    cli.lote = lambda eventos: _Resp(main.save_events(eventos))

    def linhas():
        conn = sqlite3.connect(caminho)
        conn.row_factory = sqlite3.Row
        try:
            return {r["id"]: dict(r) for r in conn.execute("SELECT * FROM crises")}
        finally:
            conn.close()

    cli.linhas = linhas
    return cli


EVENTO = {"id": "t-1", "title": "Terremoto", "country": "Chile", "country_iso3": "CHL", "lat": -33.4,
          "lon": -70.6, "severity": 4, "urgency": "immediate", "crisis_type": "seismic",
          "source": "teste", "people_affected": 1200}


# ---------- formato aceito ----------

def test_save_events_aceita_lista_e_insere(api):
    r = api.lote([EVENTO])
    assert r.json() == {"ok": True, "saved": 1, "errors": []}
    linha = api.linhas()["t-1"]
    assert (linha["title"], linha["country_iso3"], linha["severity"], linha["crisis_type"]) == ("Terremoto", "CHL", 4, "seismic")
    assert linha["people_affected"] == 1200 and linha["source"] == "teste"


def test_save_events_http_recusa_json_em_lista_hoje(api):
    # `events: list` sem tipo de item vira campo de formulário no FastAPI 0.165: o POST JSON do
    # tools/save_classification.py (json=[payload]) leva 422 e nada é gravado.
    r = api.post("/save_events", json=[EVENTO])
    assert r.status_code == 422
    assert api.linhas() == {}


def test_save_events_http_recusa_dict(api):
    assert api.post("/save_events", json=EVENTO).status_code == 422


def test_save_event_aceita_dict_e_devolve_id(api):
    r = api.post("/save_event", json=EVENTO)
    assert r.json() == {"ok": True, "id": "t-1"}
    assert "t-1" in api.linhas()


def test_save_event_rejeita_lista(api):
    assert api.post("/save_event", json=[EVENTO]).status_code == 422


# ---------- type / crisis_type ----------

def test_crisis_type_nao_e_normalizado_hoje(api):
    api.lote([{**EVENTO, "crisis_type": "  Seismic "}])
    assert api.linhas()["t-1"]["crisis_type"] == "  Seismic "


def test_campo_type_e_ignorado_hoje(api):
    evento = {k: v for k, v in EVENTO.items() if k != "crisis_type"}
    api.lote([{**evento, "type": "seismic"}])
    assert api.linhas()["t-1"]["crisis_type"] == "humanitarian"  # padrão; "type" não é lido


def test_crisis_type_fora_do_schema_e_aceito_hoje(api):
    r = api.lote([{**EVENTO, "crisis_type": "banana"}])
    assert r.json() == {"ok": True, "saved": 1, "errors": []}
    assert api.linhas()["t-1"]["crisis_type"] == "banana"


def test_save_event_crisis_type_fora_do_schema_e_aceito_hoje(api):
    assert api.post("/save_event", json={**EVENTO, "crisis_type": "banana"}).json()["ok"] is True
    assert api.linhas()["t-1"]["crisis_type"] == "banana"


# ---------- campos ausentes ----------

def test_campos_ausentes_recebem_padroes(api):
    r = api.lote([{}])
    assert r.json()["saved"] == 1
    (eid, linha), = api.linhas().items()
    assert eid.startswith("api-")
    assert (linha["title"], linha["country"], linha["country_iso3"]) == ("", "", "UNK")
    assert (linha["lat"], linha["lon"], linha["severity"]) == (0, 0, 1)
    assert (linha["urgency"], linha["crisis_type"], linha["source"], linha["people_affected"]) == ("monitoring", "humanitarian", "api", 0)


def test_dois_eventos_sem_id_no_mesmo_lote_viram_duas_linhas(api):
    assert api.lote([{}, {}]).json()["saved"] == 2
    assert len(api.linhas()) == 2


# ---------- INSERT x UPDATE e id duplicado ----------

def test_id_existente_atualiza_so_severity_urgency_e_tipo(api):
    api.lote([EVENTO])
    r = api.lote([{**EVENTO, "title": "Outro", "severity": 2, "urgency": "48h",
                                         "crisis_type": "wildfire", "people_affected": 9}])
    assert r.json() == {"ok": True, "saved": 0, "errors": []}  # UPDATE não conta em "saved"
    linha = api.linhas()["t-1"]
    assert (linha["severity"], linha["urgency"], linha["crisis_type"]) == (2, "48h", "wildfire")
    assert (linha["title"], linha["people_affected"]) == ("Terremoto", 1200)


def test_save_event_id_existente_atualiza(api):
    api.post("/save_event", json=EVENTO)
    assert api.post("/save_event", json={**EVENTO, "severity": 1}).json() == {"ok": True, "id": "t-1"}
    assert api.linhas()["t-1"]["severity"] == 1


def test_id_duplicado_no_lote_insere_uma_vez_e_atualiza_com_o_ultimo(api):
    r = api.lote([EVENTO, {**EVENTO, "severity": 5}])
    assert r.json()["saved"] == 1
    assert len(api.linhas()) == 1 and api.linhas()["t-1"]["severity"] == 5


# ---------- erros ----------

def test_evento_com_erro_nao_derruba_o_lote(api):
    r = api.lote([{**EVENTO, "id": "ruim", "lat": "abc"}, {**EVENTO, "id": "bom"}])
    corpo = r.json()
    assert corpo["ok"] is True and corpo["saved"] == 1
    assert [e["id"] for e in corpo["errors"]] == ["ruim"]
    assert set(api.linhas()) == {"bom"}


def test_save_event_com_erro_devolve_ok_false(api):
    r = api.post("/save_event", json={**EVENTO, "lat": "abc"})
    assert r.status_code == 200 and r.json()["ok"] is False and "error" in r.json()
