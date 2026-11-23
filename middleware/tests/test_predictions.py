"""GET /predictions sobre prever_risco: cache de 1 h só para resultado válido; falha -> 200 degradado."""
import json

import pytest
from fastapi.testclient import TestClient

from middleware import llm
from middleware.gravacao import gravar_eventos
from middleware.llm import LLMIndisponivel
from middleware.tests.falsos import ProvedorFalso, diz


def previsao_ok(local="Valparaíso"):
    return diz(json.dumps({"predictions": [{
        "location": local, "country": "Chile", "risk_type": "seismic", "probability": "high",
        "timeframe_days": 14, "recommended_action": "Pré-posicionar equipes", "justification": "Réplicas."}]}))


@pytest.fixture(autouse=True)
def sem_provedor_global():
    llm.definir_provedor(None)
    llm._padrao = None
    llm._uso.update(dia=None, n=0)
    yield
    llm.definir_provedor(None)


@pytest.fixture
def cli(app_db):
    db = app_db.get_db()
    gravar_eventos(db, [{"id": "e1", "title": "Terremoto", "country": "Chile", "severity": 4,
                         "urgency": "24h", "crisis_type": "seismic", "source": "usgs"}])
    db.close()
    app_db._predictions_cache.update(data=None, ts=0)
    return TestClient(app_db.app)


def usar(roteiro):
    p = ProvedorFalso(roteiro)
    llm.definir_provedor(p)
    return p


def test_valido_e_cacheado_segunda_chamada_nao_chama_o_llm(cli):
    p = usar([previsao_ok()])
    a = cli.get("/predictions").json()
    b = cli.get("/predictions").json()
    assert a == b and len(a["predictions"]) == 1 and "degradado" not in a
    assert len(p.chamadas) == 1


def test_cache_expirado_chama_o_llm_de_novo(cli, app_db):
    p = usar([previsao_ok("A"), previsao_ok("B")])
    cli.get("/predictions")
    app_db._predictions_cache["ts"] -= 3601
    assert cli.get("/predictions").json()["predictions"][0]["location"] == "B"
    assert len(p.chamadas) == 2


def test_erro_nao_e_cacheado_segunda_chamada_tenta_de_novo(cli):
    p = usar([diz("não é JSON"), previsao_ok()])
    a = cli.get("/predictions")
    assert a.status_code == 200
    assert a.json()["predictions"] == [] and a.json()["degradado"] is True and a.json()["error"]
    b = cli.get("/predictions").json()
    assert len(b["predictions"]) == 1 and len(p.chamadas) == 2


def test_llm_indisponivel_e_teto_diario_viram_200_degradado_sem_cache(cli, app_db, monkeypatch):
    usar([LLMIndisponivel("falha do provedor: APIError"), previsao_ok()])
    r = cli.get("/predictions")
    assert r.status_code == 200
    assert r.json() == {"predictions": [], "error": "Previsões indisponíveis no momento.", "degradado": True}
    assert len(cli.get("/predictions").json()["predictions"]) == 1
    # teto diário
    monkeypatch.setenv("CRISIS_LLM_LIMITE_DIARIO", "1")
    llm._uso.update(dia=None, n=0)
    app_db._predictions_cache.update(data=None, ts=0)
    usar([previsao_ok(), previsao_ok()])
    assert "degradado" not in cli.get("/predictions").json()
    app_db._predictions_cache.update(data=None, ts=0)
    r = cli.get("/predictions")
    assert r.status_code == 200 and r.json()["degradado"] is True


def test_resultado_vazio_sem_erro_nao_e_cacheado(cli):
    p = usar([diz('{"predictions": []}'), previsao_ok()])
    assert cli.get("/predictions").json()["predictions"] == []
    assert len(cli.get("/predictions").json()["predictions"]) == 1 and len(p.chamadas) == 2


def test_excecao_inesperada_vira_200_degradado(cli, app_db, monkeypatch):
    monkeypatch.setattr(app_db, "prever_risco", lambda *a, **k: 1 / 0)
    r = cli.get("/predictions")
    assert r.status_code == 200 and r.json()["degradado"] is True and "division" not in str(r.json())


def test_falha_com_cache_expirado_serve_stale(cli, app_db):
    usar([previsao_ok("A"), LLMIndisponivel("fora")])
    cli.get("/predictions")
    app_db._predictions_cache["ts"] -= 3601
    r = cli.get("/predictions").json()
    assert r["stale"] is True and r["degradado"] is True and r["predictions"][0]["location"] == "A"
    assert app_db._predictions_cache["data"]["predictions"][0]["location"] == "A"
    assert "stale" not in app_db._predictions_cache["data"]  # o cache guarda só o válido original


def test_sem_eventos_mantem_a_nota_e_nao_chama_o_llm(app_db):
    p = usar([])
    app_db._predictions_cache.update(data=None, ts=0)
    r = TestClient(app_db.app).get("/predictions").json()
    assert r == {"predictions": [], "note": "Sem eventos no banco de dados"} and p.chamadas == []
