import importlib
import os
import socket
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
for p in (RAIZ, os.path.join(RAIZ, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    """NFR-003: nenhum teste acessa a rede."""
    original = socket.socket.connect

    def bloquear(self, endereco):
        host = endereco[0] if isinstance(endereco, tuple) else endereco
        if host not in ("127.0.0.1", "localhost", "::1") and not str(host).startswith("/"):
            raise RuntimeError(f"teste tentou acessar a rede: {endereco}")
        return original(self, endereco)

    monkeypatch.setattr(socket.socket, "connect", bloquear)


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    crisis = tmp_path / "crisis.db"
    crisis.write_bytes(b"")
    monkeypatch.setenv("DB_PATH", str(crisis))
    monkeypatch.setenv("BRASIL_DB_PATH", str(tmp_path / "brasil.db"))
    monkeypatch.setenv("BRASIL_DEV_LOGIN", "1")
    for k in ("BRASIL_ORQUESTRADOR", "BRASIL_INGESTAO_AUTO_MIN", "BRASIL_NOTIFICACOES"):
        monkeypatch.delenv(k, raising=False)
    import middleware.brasil.db as db
    db._prontos.clear()
    return tmp_path


@pytest.fixture
def api(ambiente):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import middleware.brasil.rotas as rotas
    importlib.reload(rotas)
    app = FastAPI()
    app.include_router(rotas.router)
    return TestClient(app), rotas
