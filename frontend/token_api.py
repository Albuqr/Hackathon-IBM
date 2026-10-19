"""Cabeçalho do segredo da API para quem chama o middleware (cópia mínima de middleware/seguranca.py,
porque a imagem do frontend não leva o pacote middleware). Um teste garante que os dois derivam o mesmo token."""
import hashlib
import hmac
import os

CABECALHO = "X-Crisis-Token"
PADRAO_DEV = "hktn26-dev-secret"


def cabecalhos() -> dict:
    s = os.environ.get("SECRET_KEY", "")
    if not s or s == PADRAO_DEV:
        return {}
    return {CABECALHO: hmac.new(s.encode(), b"crisis-api-v1", hashlib.sha256).hexdigest()}
