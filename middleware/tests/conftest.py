import importlib
import os
import sqlite3
import subprocess
import sys
import types

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    """middleware.main recarregado sobre um SQLite temporário (init_db.py). Devolve (main, linhas())."""
    (tmp_path / "data").mkdir()
    subprocess.run([sys.executable, os.path.join(RAIZ, "init_db.py")], cwd=tmp_path, check=True, capture_output=True)
    caminho = tmp_path / "data" / "crisis.db"
    monkeypatch.setenv("DB_PATH", str(caminho))
    monkeypatch.setenv("BRASIL_DB_PATH", str(tmp_path / "brasil.db"))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("MONITORING_AGENT_ID", raising=False)
    monkeypatch.delenv("ORCHESTRATOR_AGENT_ID", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    sys.path.insert(0, os.path.join(RAIZ, "tools"))
    # Telegram: nada de rede; registra os avisos
    avisos = []

    async def broadcast_to_subscribers(**kw):
        avisos.append(kw)
    falso = types.ModuleType("notify_telegram")
    falso.broadcast_to_subscribers = broadcast_to_subscribers
    monkeypatch.setitem(sys.modules, "notify_telegram", falso)
    import middleware.main as main
    main = importlib.reload(main)

    def linhas():
        conn = sqlite3.connect(caminho)
        conn.row_factory = sqlite3.Row
        try:
            return {r["id"]: dict(r) for r in conn.execute("SELECT * FROM crises")}
        finally:
            conn.close()
    main.linhas, main.avisos = linhas, avisos
    return main
