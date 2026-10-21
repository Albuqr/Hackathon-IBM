"""VPS_API_URL não tem mais um IP público como padrão: sem ela, /ingest usa o caminho direto."""
import importlib
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture
def main(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir(exist_ok=True)
    subprocess.run([sys.executable, os.path.join(RAIZ, "init_db.py")], cwd=tmp_path, check=True, capture_output=True)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "crisis.db"))
    monkeypatch.setenv("BRASIL_DB_PATH", str(tmp_path / "brasil.db"))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    sys.path.insert(0, os.path.join(RAIZ, "tools"))
    import middleware.main as m
    return importlib.reload(m)


def _ingest(main, monkeypatch, vps_url):
    chamadas = []
    monkeypatch.setenv("MONITORING_AGENT_ID", "agente-de-teste")
    if vps_url is None:
        monkeypatch.delenv("VPS_API_URL", raising=False)
    else:
        monkeypatch.setenv("VPS_API_URL", vps_url)
    monkeypatch.setattr(main, "call_orchestrate", lambda message, **kw: chamadas.append(message) or {"ok": True})
    monkeypatch.setattr(main, "_ingest_fallback", lambda: {"ok": True, "triggered_by": "fallback"})
    r = TestClient(main.app).post("/ingest")
    return r.json(), chamadas


def test_sem_vps_api_url_o_ingest_usa_o_caminho_direto(main, monkeypatch):
    corpo, chamadas = _ingest(main, monkeypatch, None)
    assert corpo["triggered_by"] == "fallback" and chamadas == []


def test_com_vps_api_url_o_agente_recebe_a_url_configurada(main, monkeypatch):
    corpo, chamadas = _ingest(main, monkeypatch, "https://api.exemplo.test")
    assert corpo["triggered_by"] == "orchestrate"
    assert "https://api.exemplo.test" in chamadas[0] and "31.97.83.21" not in chamadas[0]


def test_tool_save_classification_sem_url_devolve_erro_claro(monkeypatch):
    import json
    monkeypatch.delenv("VPS_API_URL", raising=False)
    sys.path.insert(0, os.path.join(RAIZ, "tools"))
    import save_classification as sc
    sc = importlib.reload(sc)
    funcao = getattr(sc.save_classification, "__wrapped__", sc.save_classification)  # o @tool pode embrulhar
    saida = funcao(json.dumps({"id": "e1"}), json.dumps({"severity": 3}))
    saida = getattr(saida, "content", saida)  # o SDK novo devolve ToolResponse(content=...)
    if isinstance(saida, str):
        saida = json.loads(saida)
    assert saida["status"] == "error" and "VPS_API_URL" in saida["message"]
