"""ADR 0004: segredo da API no app do Crisis inteiro (FR-025, FR-026, FR-027)."""
import importlib
import logging
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture
def app_crisis(tmp_path, monkeypatch):
    def montar(secret_key=None):
        (tmp_path / "data").mkdir(exist_ok=True)
        subprocess.run([sys.executable, os.path.join(RAIZ, "init_db.py")], cwd=tmp_path, check=True, capture_output=True)
        monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "crisis.db"))
        monkeypatch.setenv("BRASIL_DB_PATH", str(tmp_path / "brasil.db"))
        if secret_key is None:
            monkeypatch.delenv("SECRET_KEY", raising=False)
        else:
            monkeypatch.setenv("SECRET_KEY", secret_key)
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
        sys.path.insert(0, os.path.join(RAIZ, "tools"))
        import middleware.main as main
        return TestClient(importlib.reload(main).app)
    return montar


# AC-025.1 (brasil-app)
def test_ac_025_1_sem_token_401_com_token_200_saude_livre(app_crisis):
    from middleware.seguranca import token
    cli = app_crisis("chave-de-teste-123")
    assert cli.get("/events").status_code == 401
    assert cli.get("/events", headers={"X-Crisis-Token": "errado"}).status_code == 401
    assert cli.get("/events", headers={"X-Crisis-Token": token("chave-de-teste-123")}).status_code == 200
    assert cli.get("/").status_code == 200
    assert cli.get("/brasil/saude").status_code == 200
    assert cli.get("/brasil/crises").status_code == 401


# AC-026.1 (brasil-app)
def test_ac_026_1_sem_secret_key_api_aberta_com_aviso(app_crisis, caplog):
    with caplog.at_level(logging.WARNING, logger="crisis.seguranca"):
        cli = app_crisis(None)
    assert cli.get("/events").status_code == 200
    assert "API sem proteção" in caplog.text


def test_padrao_de_desenvolvimento_conta_como_aberta(app_crisis):
    assert app_crisis("hktn26-dev-secret").get("/events").status_code == 200


def test_save_events_aceito_sem_token_na_transicao_com_aviso(app_crisis, caplog):
    cli = app_crisis("chave-de-teste-123")
    with caplog.at_level(logging.WARNING, logger="crisis.seguranca"):
        r = cli.post("/save_events", json=[])
    assert r.status_code != 401  # passou pela checagem (o corpo vazio não importa aqui)
    assert "sem X-Crisis-Token" in caplog.text
    assert "chave-de-teste-123" not in caplog.text  # NFR-004


# AC-027.1 (brasil-app)
def test_ac_027_1_comando_imprime_token_que_a_api_aceita(app_crisis):
    out = subprocess.run([sys.executable, "-m", "middleware.seguranca"], cwd=RAIZ, capture_output=True, text=True,
                         env={**os.environ, "SECRET_KEY": "abc-chave-xyz"})
    tok = out.stdout.strip()
    assert out.returncode == 0 and tok and "abc-chave-xyz" not in tok
    cli = app_crisis("abc-chave-xyz")
    assert cli.get("/events", headers={"X-Crisis-Token": tok}).status_code == 200


def test_token_nao_ascii_da_401_e_nao_500(app_crisis):
    cli = app_crisis("chave-de-teste-123")
    assert cli.get("/events", headers={"X-Crisis-Token": "é".encode("latin-1")}).status_code == 401


def test_frontend_e_bot_mandam_o_mesmo_token_que_a_api_aceita(monkeypatch):
    """O bot e o frontend usam frontend/token_api.py; a API valida com middleware/seguranca.py."""
    from middleware.seguranca import token
    monkeypatch.setenv("SECRET_KEY", "k-123-segredo")
    monkeypatch.setenv("TG_TOKEN", "")
    sys.path.insert(0, os.path.join(RAIZ, "frontend"))
    import token_api
    assert token_api.cabecalhos() == {"X-Crisis-Token": token("k-123-segredo")}
    import importlib.util
    spec = importlib.util.spec_from_file_location("bot_teste", os.path.join(RAIZ, "telegram_bot", "bot.py"))
    bot = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(bot)
    except ModuleNotFoundError as e:  # python-telegram-bot não está no ambiente de teste
        pytest.skip(f"bot sem dependências: {e}")
    assert bot.requests.headers["X-Crisis-Token"] == token("k-123-segredo")
