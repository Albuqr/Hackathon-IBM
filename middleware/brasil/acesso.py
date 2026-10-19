"""Quem está chamando a API do Brasil (ADR 0004, FR-024).

O frontend encaminha a identidade da sessão no cabeçalho X-Brasil-Usuario; a chamada só chega
aqui com o segredo da API (middleware/seguranca.py). O papel vem do brasil.db, nunca do corpo.
"""
from fastapi import Depends, Header, HTTPException

from . import db
from .config import Config

CABECALHO = "X-Brasil-Usuario"


class Acesso:
    def __init__(self, cfg: Config):
        self.cfg = cfg

        def identidade(x_brasil_usuario: int | None = Header(None)) -> dict:
            if x_brasil_usuario is None:
                raise HTTPException(401, "Entre para continuar")
            conn = db.conectar(cfg)
            try:
                u = conn.execute("SELECT id, role FROM users WHERE id=?", (x_brasil_usuario,)).fetchone()
            finally:
                conn.close()
            if not u:
                raise HTTPException(401, "Usuário desconhecido")
            return dict(u)

        self.identidade = identidade

    def exige(self, *papeis: str):
        """Dependência: usuário identificado e, se dados, com um destes papéis."""
        def dep(u: dict = Depends(self.identidade)) -> dict:
            if papeis and u["role"] not in papeis:
                raise HTTPException(403, "Seu perfil não pode fazer isto")
            return u
        return dep

    @staticmethod
    def proprio(u: dict, uid: int):
        """Só o próprio usuário (ou o admin) acessa dados deste uid."""
        if u["id"] != uid and u["role"] != "admin":
            raise HTTPException(403, "Estes dados são de outro usuário")
