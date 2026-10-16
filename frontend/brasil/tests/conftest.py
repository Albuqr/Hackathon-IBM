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
    """Substitui a API /brasil: registra as chamadas e devolve respostas fixas."""
    def __init__(self):
        self.chamadas = []
        self.respostas = {}

    def __call__(self, metodo, caminho, timeout=30, **kw):
        self.chamadas.append((metodo, caminho, kw.get("json")))
        for (m, prefixo), resp in self.respostas.items():
            if m == metodo and caminho.startswith(prefixo):
                return resp
        return 404, {"detail": "Não encontrado"}


@pytest.fixture
def front(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "crisis.db"))
    # middleware/brasil e frontend/brasil têm o mesmo nome: garante o do frontend (como em produção,
    # onde cada um roda no seu processo).
    frontend = os.path.join(RAIZ, "frontend")
    carregado = sys.modules.get("brasil")
    if carregado is not None and not os.path.abspath(carregado.__file__).startswith(frontend + os.sep):
        monkeypatch.delitem(sys.modules, "brasil")
    monkeypatch.syspath_prepend(frontend)
    import app as crisis_app
    falsa = ApiFalsa()
    # o módulo que o app realmente usa (o blueprint registrado na importação do app.py)
    monkeypatch.setitem(modulo_do_blueprint(crisis_app.app), "api", falsa)
    crisis_app.app.config["TESTING"] = True
    return crisis_app.app.test_client(), falsa


def modulo_do_blueprint(app) -> dict:
    return app.view_functions["brasil.inicio"].__globals__


@pytest.fixture
def logar():
    def entrar(cli, papel="volunteer", uid=7):
        with cli.session_transaction() as s:
            s["br_user_id"], s["br_role"], s["br_nome"] = uid, papel, "Teste"
    return entrar
