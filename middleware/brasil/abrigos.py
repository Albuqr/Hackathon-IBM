"""Abrigos do gestor de abrigo (ADR 0005).

O abrigo funciona assim que é criado, marcado "não verificado". Só o gestor dono vê e edita o abrigo;
abrigo de outro gestor responde 404 (não revela que existe). A verificação de verdade ainda não existe:
`POST /dev/abrigos/{id}/verificar` só responde com BRASIL_DEV_LOGIN=1 e sempre 404 em produção.

`abrigo_do_gestor` e `gestor_verificado` são reusados pelos módulos de abrigados e estoque.
"""
import math
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from . import db, malha
from .acesso import Acesso
from .config import Config

PAPEL = "gestor_abrigo"
TIPOS = ("permanente", "temporario")

SQL_ABRIGO = (
    "SELECT id, gestor_id, nome, endereco, lat, lon, municipio_ibge, uf, capacidade, tipo, ativo, sensivel, "
    "verificado, verificado_em, criado_em FROM abrigos WHERE id=?"
)
SQL_MEUS = (
    "SELECT id, gestor_id, nome, endereco, lat, lon, municipio_ibge, uf, capacidade, tipo, ativo, sensivel, "
    "verificado, verificado_em, criado_em FROM abrigos WHERE gestor_id=? ORDER BY id"
)


class DadosAbrigo(BaseModel):
    nome: str = Field(min_length=2, max_length=200)
    endereco: str = Field("", max_length=300)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    capacidade: int = Field(gt=0, le=100000)
    tipo: Literal["permanente", "temporario"]
    ativo: bool = True
    sensivel: bool = False
    crises: list[str] | None = None  # None na edição = mantém os vínculos


def abrigo_do_gestor(conn, abrigo_id: int, u: dict) -> dict:
    """O abrigo, se for deste gestor. Inexistente ou de outro gestor → 404 (mesma resposta, não revela)."""
    r = conn.execute(SQL_ABRIGO, (abrigo_id,)).fetchone()
    if not r or r["gestor_id"] != u["id"]:
        raise HTTPException(404, "Abrigo não encontrado")
    return dict(r)


def gestor_verificado(conn, uid: int) -> bool:
    """Verdadeiro se algum abrigo deste gestor estiver verificado."""
    return conn.execute("SELECT 1 FROM abrigos WHERE gestor_id=? AND verificado=1 LIMIT 1", (uid,)).fetchone() is not None


def local(lat: float, lon: float) -> dict:
    """Município IBGE do ponto; fora do Brasil → 422."""
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise HTTPException(422, "Latitude e longitude inválidas")
    cod = malha.carregar().municipio_em(lat, lon)
    if cod is None:
        raise HTTPException(422, "A localização precisa estar no Brasil")
    info = malha.carregar().info(cod) or {}
    return {"municipio_ibge": cod, "municipio": info.get("nome"), "uf": info.get("uf")}


def _crises_validas(conn, ids: list[str]) -> list[str]:
    limpos = list(dict.fromkeys(i.strip() for i in ids if i and i.strip()))
    faltam = [i for i in limpos if not conn.execute("SELECT 1 FROM crises WHERE id=?", (i,)).fetchone()]
    if faltam:
        raise HTTPException(422, f"Crise não encontrada: {', '.join(faltam)}")
    return limpos


def _vincular(conn, abrigo_id: int, ids: list[str]):
    conn.execute("DELETE FROM abrigo_crises WHERE abrigo_id=?", (abrigo_id,))
    conn.executemany("INSERT INTO abrigo_crises (abrigo_id, crisis_id) VALUES (?,?)", [(abrigo_id, i) for i in ids])


def completo(conn, a: dict) -> dict:
    """Abrigo para a resposta: booleanos, nome do município e crises vinculadas."""
    a = dict(a)
    for k in ("ativo", "sensivel", "verificado"):
        a[k] = bool(a[k])
    info = malha.carregar().info(a["municipio_ibge"]) if a.get("municipio_ibge") else None
    a["municipio"] = info.get("nome") if info else None
    a["crises"] = [dict(r) for r in conn.execute(
        """SELECT c.id, c.title, c.uf FROM abrigo_crises ac JOIN crises c ON c.id=ac.crisis_id
           WHERE ac.abrigo_id=? ORDER BY c.title""", (a["id"],))]
    # abrigados (ADR 0006): só a contagem, nunca dados das pessoas
    a["presentes"] = conn.execute("SELECT COUNT(*) FROM abrigados WHERE abrigo_id=? AND saida_em IS NULL", (a["id"],)).fetchone()[0]
    return a


def criar_router(cfg: Config, acesso: Acesso) -> APIRouter:
    r = APIRouter()
    gestor = acesso.exige(PAPEL)

    def conectar():
        return db.conectar(cfg)

    @r.get("/abrigos")
    def meus_abrigos(u: dict = Depends(gestor)):
        conn = conectar()
        try:
            return [completo(conn, a) for a in conn.execute(SQL_MEUS, (u["id"],))]
        finally:
            conn.close()

    @r.get("/abrigos/municipio")
    def municipio_do_ponto(lat: float, lon: float, u: dict = Depends(gestor)):
        """Para a etapa Local: mostra o município antes de criar."""
        return local(lat, lon)

    @r.post("/abrigos")
    def criar_abrigo(d: DadosAbrigo, u: dict = Depends(gestor)):
        lugar = local(d.lat, d.lon)
        conn = conectar()
        try:
            crises = _crises_validas(conn, d.crises or [])
            cur = conn.execute(
                """INSERT INTO abrigos (gestor_id, nome, endereco, lat, lon, municipio_ibge, uf, capacidade, tipo, ativo, sensivel)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (u["id"], d.nome.strip(), d.endereco.strip(), d.lat, d.lon, lugar["municipio_ibge"], lugar["uf"],
                 d.capacidade, d.tipo, int(d.ativo), int(d.sensivel)))
            _vincular(conn, cur.lastrowid, crises)
            conn.commit()
            return completo(conn, abrigo_do_gestor(conn, cur.lastrowid, u))
        finally:
            conn.close()

    @r.get("/abrigos/{abrigo_id}")
    def obter_abrigo(abrigo_id: int, u: dict = Depends(gestor)):
        conn = conectar()
        try:
            return completo(conn, abrigo_do_gestor(conn, abrigo_id, u))
        finally:
            conn.close()

    @r.put("/abrigos/{abrigo_id}")
    def editar_abrigo(abrigo_id: int, d: DadosAbrigo, u: dict = Depends(gestor)):
        """Edita os dados do abrigo; a verificação não muda por aqui."""
        conn = conectar()
        try:
            abrigo_do_gestor(conn, abrigo_id, u)
            lugar = local(d.lat, d.lon)
            crises = _crises_validas(conn, d.crises) if d.crises is not None else None
            conn.execute(
                """UPDATE abrigos SET nome=?, endereco=?, lat=?, lon=?, municipio_ibge=?, uf=?, capacidade=?, tipo=?,
                   ativo=?, sensivel=? WHERE id=?""",
                (d.nome.strip(), d.endereco.strip(), d.lat, d.lon, lugar["municipio_ibge"], lugar["uf"], d.capacidade,
                 d.tipo, int(d.ativo), int(d.sensivel), abrigo_id))
            if crises is not None:
                _vincular(conn, abrigo_id, crises)
            conn.commit()
            return completo(conn, abrigo_do_gestor(conn, abrigo_id, u))
        finally:
            conn.close()

    @r.post("/dev/abrigos/{abrigo_id}/verificar")
    def dev_verificar(abrigo_id: int, x_brasil_usuario: int | None = Header(None)):
        """Só para testes (BRASIL_DEV_LOGIN=1): alterna verificado/não verificado do próprio abrigo.
        Sem o login de teste, 404 antes de qualquer outra checagem."""
        if not cfg.dev_login:
            raise HTTPException(404, "Não encontrado")
        u = acesso.identidade(x_brasil_usuario)
        if u["role"] != PAPEL:
            raise HTTPException(404, "Não encontrado")
        conn = conectar()
        try:
            a = abrigo_do_gestor(conn, abrigo_id, u)
            novo = 0 if a["verificado"] else 1
            conn.execute("UPDATE abrigos SET verificado=?, verificado_em=? WHERE id=?",
                         (novo, datetime.now(timezone.utc).isoformat() if novo else None, abrigo_id))
            conn.commit()
            return completo(conn, abrigo_do_gestor(conn, abrigo_id, u))
        finally:
            conn.close()

    return r
