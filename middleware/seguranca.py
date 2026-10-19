"""Segredo da API (ADR 0004).

Quem chama a API (frontend, bot do Telegram, tools do watsonx) manda o cabeçalho X-Crisis-Token.
O token é derivado do SECRET_KEY que já existe no .env, então não há variável nova; o valor bruto
do SECRET_KEY nunca trafega. Sem SECRET_KEY (ou com o padrão de desenvolvimento) a API fica aberta,
como antes, com um aviso na subida.

Uso: python -m middleware.seguranca   → imprime o token, para a conexão das tools no watsonx.
"""
import hashlib
import hmac
import logging
import os

from fastapi.responses import JSONResponse

CABECALHO = "X-Crisis-Token"
PADRAO_DEV = "hktn26-dev-secret"  # o mesmo de frontend/app.py
ROTULO = b"crisis-api-v1"
ISENTOS = {("GET", "/"), ("GET", "/brasil/saude")}
# Exceção temporária: as tools do watsonx ainda não mandam o token. Sai quando forem republicadas.
TRANSICAO = {("POST", "/save_events")}

log = logging.getLogger("crisis.seguranca")


def token(secret_key: str) -> str:
    return hmac.new(secret_key.encode(), ROTULO, hashlib.sha256).hexdigest()


def segredo(env=None) -> str | None:
    """SECRET_KEY válido para proteger a API, ou None se a API deve ficar aberta."""
    valor = (os.environ if env is None else env).get("SECRET_KEY", "")
    return valor if valor and valor != PADRAO_DEV else None


def cabecalhos(env=None) -> dict:
    """Cabeçalhos que quem chama a API deve mandar ({} quando a proteção está desligada)."""
    s = segredo(env)
    return {CABECALHO: token(s)} if s else {}


def instalar(app):
    """Registra a checagem no app FastAPI. Avisa uma vez, na subida, se ficou aberta."""
    if segredo() is None:
        log.warning("API sem proteção: defina SECRET_KEY (diferente do padrão) para exigir %s", CABECALHO)

    @app.middleware("http")
    async def exigir_token(request, call_next):
        s = segredo()
        chave = (request.method, request.url.path)
        if s is None or request.method == "OPTIONS" or chave in ISENTOS:
            return await call_next(request)
        recebido = request.headers.get(CABECALHO, "")
        if hmac.compare_digest(recebido.encode(), token(s).encode()):
            return await call_next(request)
        if chave in TRANSICAO:
            log.warning("%s %s sem %s (aceito na transição)", *chave, CABECALHO)
            return await call_next(request)
        return JSONResponse({"detail": "Não autorizado"}, status_code=401)

    return app


if __name__ == "__main__":
    s = segredo()
    if s is None:
        raise SystemExit("SECRET_KEY ausente ou igual ao padrão de desenvolvimento: a API está aberta.")
    print(token(s))
