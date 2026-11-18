"""Estoque e necessidades do abrigo (ADR 0007).

A lista de itens é uma só para todos os abrigos e cresce: o gestor que não acha o item cria um novo (nome, grupo,
unidade) e ele passa a aparecer para todos. Cada abrigo marca, por item, o status (Urgente/Precisa/OK/Sobrando) e uma
quantidade aproximada. Profissionais e veículos são só pedidos (Urgente/Precisa com quantos precisa), nunca estoque.

Duplicados: o mesmo nome normalizado reaproveita o item que existe; nomes parecidos ("agua" e "Água mineral") só são
sinalizados pelo agente `itens_duplicados` (regra local em `orquestracao`), nunca unidos nem renomeados.
"""
import difflib
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db, orquestracao
from .abrigos import PAPEL, abrigo_do_gestor
from .acesso import Acesso
from .config import Config

GRUPOS = {
    "sustento": "Sustento",
    "profissionais": "Profissionais",
    "energia_mobilidade": "Energia e Mobilidade",
    "estrutura_ativos": "Estrutura e Ativos",
}
STATUS = {"urgente": "Urgente", "precisa": "Precisa", "ok": "OK", "sobrando": "Sobrando"}
SO_PEDIDO = ("urgente", "precisa")
SO_PEDIDO_MSG = "Profissionais e veículos são só pedidos: marque Urgente ou Precisa."
QUANTOS_MSG = "Informe quantos precisa (um número maior que zero)."
LIMITE_SUGESTOES = 10
LIMITE_DUPLICADOS = 5
SEMELHANCA = 0.8
_VAZIAS = {"a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "para", "com"}

SQL_ITEM = "SELECT id, nome, grupo, unidade, so_necessidade FROM itens WHERE id=?"
SQL_TODOS = "SELECT id, nome, grupo, unidade, so_necessidade FROM itens ORDER BY id"
SQL_SUGESTOES = (
    "SELECT id, nome, grupo, unidade, so_necessidade FROM itens WHERE instr(nome_busca, ?) > 0 "
    "ORDER BY instr(nome_busca, ?) = 1 DESC, instr(' ' || nome_busca, ' ' || ?) > 0 DESC, nome_busca LIMIT ?"
)
SQL_ESTOQUE = (
    "SELECT i.id, i.nome, i.grupo, i.unidade, i.so_necessidade, ai.status, ai.quantidade, ai.atualizado_em "
    "FROM abrigo_itens ai JOIN itens i ON i.id=ai.item_id WHERE ai.abrigo_id=? ORDER BY i.nome_busca"
)
SQL_LINHA = (
    "SELECT i.id, i.nome, i.grupo, i.unidade, i.so_necessidade, ai.status, ai.quantidade, ai.atualizado_em "
    "FROM abrigo_itens ai JOIN itens i ON i.id=ai.item_id WHERE ai.abrigo_id=? AND ai.item_id=?"
)


# ── nomes ─────────────────────────────────────────────────────────────
def normalizar(nome: str) -> str:
    """Sem acento, minúsculo, sem pontuação, espaços simples. É o `nome_busca` (único na tabela)."""
    s = unicodedata.normalize("NFKD", nome or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def _singular(t: str) -> str:
    """Plural simples do português, só para comparar ("colchoes" → "colchao", "cobertores" → "cobertor")."""
    if len(t) <= 3:
        return t
    for fim, troca in (("oes", "ao"), ("aes", "ao"), ("ns", "m"), ("res", "r"), ("zes", "z")):
        if t.endswith(fim):
            return t[: -len(fim)] + troca
    return t[:-1] if t.endswith("s") else t


def _palavras(nome: str) -> list[str]:
    return [_singular(t) for t in normalizar(nome).split() if t not in _VAZIAS]


def duplicados(nome: str, itens: list[dict], limite: int = LIMITE_DUPLICADOS) -> list[dict]:
    """Itens que parecem o mesmo que `nome`: igual sem acento/plural, um contido no outro ("agua" e "Água mineral"),
    um começo do outro, ou muito parecidos (difflib ≥ 0,8). Só sinaliza; quem decide é a pessoa."""
    a = _palavras(nome)
    if not a:
        return []
    sa, ta = " ".join(a), set(a)
    achados = []
    for it in itens:
        b = _palavras(it.get("nome", ""))
        if not b:
            continue
        sb, tb = " ".join(b), set(b)
        if sa == sb:
            nota = 1.0
        elif ta <= tb or tb <= ta:
            nota = 0.9
        elif min(len(sa), len(sb)) >= 4 and (sa.startswith(sb) or sb.startswith(sa)):
            nota = 0.85
        else:
            nota = difflib.SequenceMatcher(None, sa, sb).ratio()
            if nota < SEMELHANCA:
                continue
        achados.append((nota, it))
    achados.sort(key=lambda x: (-x[0], normalizar(x[1].get("nome", ""))))
    return [it for _, it in achados[:limite]]


# ── formato das respostas ─────────────────────────────────────────────
def _item(r) -> dict:
    d = dict(r)
    d["so_necessidade"] = bool(d["so_necessidade"])
    d["grupo_nome"] = GRUPOS.get(d["grupo"], d["grupo"])
    return d


def _linha(r) -> dict:
    d = _item(r)
    d["status_nome"] = STATUS.get(d["status"], d["status"])
    return d


def grupos() -> list[dict]:
    return [{"id": k, "nome": v} for k, v in GRUPOS.items()]


def possiveis_duplicados(cfg: Config, conn, nome: str, excluir: int | None = None) -> list[dict]:
    """Pergunta ao agente `itens_duplicados` (regra local; outro provedor cai para o local)."""
    todos = [_item(r) for r in conn.execute(SQL_TODOS) if r["id"] != excluir]
    res = orquestracao.executar(cfg, "itens_duplicados", nome, {"itens": todos})
    return list(res.dados or [])[:LIMITE_DUPLICADOS]


# ── entrada ───────────────────────────────────────────────────────────
class NovoItem(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    grupo: Literal["sustento", "profissionais", "energia_mobilidade", "estrutura_ativos"]
    unidade: str = Field(min_length=1, max_length=30)
    so_necessidade: bool | None = None  # vale só em Energia e Mobilidade (veículo = só pedido)


class Situacao(BaseModel):
    status: Literal["urgente", "precisa", "ok", "sobrando"]
    quantidade: float | None = Field(None, ge=0, le=1_000_000_000, allow_inf_nan=False)


def _so_necessidade(d: NovoItem) -> int:
    if d.grupo == "profissionais":
        return 1
    if d.grupo == "energia_mobilidade":
        return int(bool(d.so_necessidade))
    return 0


def criar_router(cfg: Config, acesso: Acesso) -> APIRouter:
    r = APIRouter()
    gestor = acesso.exige(PAPEL)

    def conectar():
        return db.conectar(cfg)

    @r.get("/itens/grupos")
    def grupos_itens(u: dict = Depends(gestor)):
        return grupos()

    @r.get("/itens/sugestoes")
    def sugerir_itens(q: str = "", u: dict = Depends(gestor)):
        """Enquanto a pessoa digita: itens cujo nome contém o texto (começo primeiro) e os possíveis duplicados."""
        busca = normalizar(q)[:80]
        if not busca:
            return {"itens": [], "exato": None, "possiveis_duplicados": []}
        conn = conectar()
        try:
            itens = [_item(x) for x in conn.execute(SQL_SUGESTOES, (busca, busca, busca, LIMITE_SUGESTOES))]
            exato = conn.execute("SELECT id FROM itens WHERE nome_busca=?", (busca,)).fetchone()
            dup = possiveis_duplicados(cfg, conn, q) if len(busca) >= 2 else []
            return {"itens": itens, "exato": exato["id"] if exato else None, "possiveis_duplicados": dup}
        finally:
            conn.close()

    @r.post("/itens")
    def criar_item(d: NovoItem, u: dict = Depends(gestor)):
        """Cria um item para todos os abrigos. Mesmo nome normalizado → devolve o que já existe (`existente`)."""
        nome = " ".join(d.nome.split())
        busca = normalizar(nome)
        if len(busca) < 2:
            raise HTTPException(422, "Informe o nome do item")
        conn = conectar()
        try:
            existe = conn.execute("SELECT id FROM itens WHERE nome_busca=?", (busca,)).fetchone()
            if existe:
                return {"item": _item(conn.execute(SQL_ITEM, (existe["id"],)).fetchone()), "existente": True,
                        "possiveis_duplicados": []}
            dup = possiveis_duplicados(cfg, conn, nome)
            try:
                cur = conn.execute(
                    "INSERT INTO itens (nome, nome_busca, grupo, unidade, so_necessidade, criado_por) VALUES (?,?,?,?,?,?)",
                    (nome, busca, d.grupo, " ".join(d.unidade.split()), _so_necessidade(d), u["id"]))
                conn.commit()
            except sqlite3.IntegrityError:  # corrida entre dois gestores criando o mesmo nome
                existe = conn.execute("SELECT id FROM itens WHERE nome_busca=?", (busca,)).fetchone()
                return {"item": _item(conn.execute(SQL_ITEM, (existe["id"],)).fetchone()), "existente": True,
                        "possiveis_duplicados": []}
            return {"item": _item(conn.execute(SQL_ITEM, (cur.lastrowid,)).fetchone()), "existente": False,
                    "possiveis_duplicados": dup}
        finally:
            conn.close()

    @r.get("/abrigos/{abrigo_id}/estoque")
    def estoque_abrigo(abrigo_id: int, u: dict = Depends(gestor)):
        conn = conectar()
        try:
            abrigo_do_gestor(conn, abrigo_id, u)
            return [_linha(x) for x in conn.execute(SQL_ESTOQUE, (abrigo_id,))]
        finally:
            conn.close()

    @r.put("/abrigos/{abrigo_id}/estoque/{item_id}")
    def atualizar_estoque(abrigo_id: int, item_id: int, d: Situacao, u: dict = Depends(gestor)):
        """Profissionais e veículos: só Urgente/Precisa e com quantos precisa. Os outros: qualquer status,
        quantidade aproximada opcional."""
        conn = conectar()
        try:
            abrigo_do_gestor(conn, abrigo_id, u)
            item = conn.execute(SQL_ITEM, (item_id,)).fetchone()
            if not item:
                raise HTTPException(404, "Item não encontrado")
            if item["so_necessidade"]:
                if d.status not in SO_PEDIDO:
                    raise HTTPException(422, SO_PEDIDO_MSG)
                if d.quantidade is None or d.quantidade <= 0:
                    raise HTTPException(422, QUANTOS_MSG)
            conn.execute(
                """INSERT INTO abrigo_itens (abrigo_id, item_id, status, quantidade, atualizado_em) VALUES (?,?,?,?,?)
                   ON CONFLICT(abrigo_id, item_id) DO UPDATE SET status=excluded.status, quantidade=excluded.quantidade,
                   atualizado_em=excluded.atualizado_em""",
                (abrigo_id, item_id, d.status, d.quantidade, datetime.now(timezone.utc).isoformat()))
            conn.commit()
            return _linha(conn.execute(SQL_LINHA, (abrigo_id, item_id)).fetchone())
        finally:
            conn.close()

    @r.delete("/abrigos/{abrigo_id}/estoque/{item_id}")
    def remover_estoque(abrigo_id: int, item_id: int, u: dict = Depends(gestor)):
        """Tira o item da lista deste abrigo (o item continua na lista compartilhada)."""
        conn = conectar()
        try:
            abrigo_do_gestor(conn, abrigo_id, u)
            n = conn.execute("DELETE FROM abrigo_itens WHERE abrigo_id=? AND item_id=?", (abrigo_id, item_id)).rowcount
            conn.commit()
            return {"ok": True, "removido": bool(n)}
        finally:
            conn.close()

    return r
