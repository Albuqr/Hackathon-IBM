import os
import socket
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
for p in (RAIZ, os.path.join(RAIZ, "frontend")):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    """NFR-003: nenhum teste acessa a rede."""
    def bloquear(self, endereco):
        raise RuntimeError(f"teste tentou acessar a rede: {endereco}")
    monkeypatch.setattr(socket.socket, "connect", bloquear)


class ApiFalsa:
    """Substitui a API /brasil (adapter em app.config["BRASIL_API"]): registra as chamadas e devolve respostas fixas."""
    def __init__(self):
        self.chamadas = []      # (metodo, caminho, usuario, json, params)
        self.respostas = {}
        self.malha = b'{"geojson":{}}'
        self.malha_pedidos = 0

    def __call__(self, metodo, caminho, usuario=None, timeout=30, **kw):
        self.chamadas.append((metodo, caminho, usuario, kw.get("json"), kw.get("params")))
        for (m, prefixo), resp in self.respostas.items():
            if m == metodo and caminho.startswith(prefixo):
                return resp
        return 404, {"detail": "Não encontrado"}

    def bruto(self, caminho, timeout=60):
        self.malha_pedidos += 1
        return self.malha


@pytest.fixture
def front(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "crisis.db"))
    # middleware/brasil e frontend/brasil têm o mesmo nome: garante o do frontend (como em produção,
    # onde cada um roda no seu processo).
    frontend = os.path.join(RAIZ, "frontend")
    for nome in [m for m in sys.modules if m == "brasil" or m.startswith("brasil.")]:
        if not os.path.abspath(sys.modules[nome].__file__ or "").startswith(frontend + os.sep):
            monkeypatch.delitem(sys.modules, nome)
    monkeypatch.syspath_prepend(frontend)
    import app as crisis_app
    falsa = ApiFalsa()
    monkeypatch.setitem(crisis_app.app.config, "BRASIL_API", falsa)
    crisis_app.app.config["TESTING"] = True
    import brasil
    brasil._malha_cache.clear()
    return crisis_app.app.test_client(), falsa


@pytest.fixture
def logar():
    def entrar(cli, papel="volunteer", uid=7):
        with cli.session_transaction() as s:
            s["br_user_id"], s["br_role"], s["br_nome"] = uid, papel, "Teste"
    return entrar
