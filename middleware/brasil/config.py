"""Configuração do Dash Brasil (spec: CFG-001 a CFG-007).

Toda opção é validada ao subir o serviço; valor inválido impede a subida com uma
mensagem que nomeia a opção, o valor e a faixa válida.
"""
import os
from dataclasses import dataclass

ORQUESTRADORES = ("local", "watsonx", "claude")
NOTIFICACOES = ("fila", "enviar")


class ConfigInvalida(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    db_path: str
    orquestrador: str
    dev_login: bool
    ingestao_auto_min: int
    notificacoes: str
    claude_modelo: str


def _db_padrao(crisis_db: str) -> str:
    return os.path.join(os.path.dirname(crisis_db) or ".", "brasil.db")


def carregar(env=None) -> Config:
    env = os.environ if env is None else env
    crisis_db = env.get("DB_PATH", "data/crisis.db")

    db_path = env.get("BRASIL_DB_PATH") or _db_padrao(crisis_db)
    if os.path.abspath(db_path) == os.path.abspath(crisis_db):
        raise ConfigInvalida(f"BRASIL_DB_PATH={db_path} é igual a DB_PATH; o Dash Brasil precisa de um banco próprio")
    pasta = os.path.dirname(os.path.abspath(db_path))
    if not os.path.isdir(pasta) or not os.access(pasta, os.W_OK):
        raise ConfigInvalida(f"BRASIL_DB_PATH={db_path}: o diretório {pasta} não existe ou não é gravável")

    orq = env.get("BRASIL_ORQUESTRADOR", "local")
    if orq not in ORQUESTRADORES:
        raise ConfigInvalida(f"BRASIL_ORQUESTRADOR={orq}; válidos: {', '.join(ORQUESTRADORES)}")

    bruto = env.get("BRASIL_DEV_LOGIN", "")
    if bruto not in ("", "1"):
        print(f"[brasil] aviso: BRASIL_DEV_LOGIN={bruto} é tratado como desligado (só '1' liga)")

    auto = env.get("BRASIL_INGESTAO_AUTO_MIN", "0")
    try:
        auto_min = int(auto)
    except ValueError:
        auto_min = -1
    if not (auto_min == 0 or 15 <= auto_min <= 1440):
        raise ConfigInvalida(f"BRASIL_INGESTAO_AUTO_MIN={auto}; use 0 ou 15–1440")

    notif = env.get("BRASIL_NOTIFICACOES", "fila")
    if notif not in NOTIFICACOES:
        raise ConfigInvalida(f"BRASIL_NOTIFICACOES={notif}; válidos: {', '.join(NOTIFICACOES)}")

    return Config(
        db_path=db_path,
        orquestrador=orq,
        dev_login=bruto == "1",
        ingestao_auto_min=auto_min,
        notificacoes=notif,
        claude_modelo=env.get("BRASIL_CLAUDE_MODELO", "claude-sonnet-5-5"),
    )
