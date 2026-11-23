"""Pessoas abrigadas (ADR 0006).

Só o gestor de abrigo usa estas rotas, e só nos próprios abrigos (abrigo de outro gestor → 404).
Nome, nome da mãe e CPF nunca saem para voluntário, ONG, admin, mapa ou log: nada aqui imprime ou loga pessoas.

Busca por nome: se algum abrigo do gestor estiver verificado, procura em todos os abrigos; senão, só nos dele.
CPF só aparece para gente dos próprios abrigos.
"""
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db, malha
from .abrigos import PAPEL, abrigo_do_gestor, gestor_verificado
from .acesso import Acesso
from .config import Config

NECESSIDADES = ("idoso", "deficiencia", "saude", "gestante")
LIMITE_BUSCA = 50
FOLGA_FUTURO = timedelta(minutes=10)  # relógio do celular adiantado; mais que isso é engano

SQL_PESSOA = ("SELECT id, abrigo_id, familia_id, nome, nome_mae, cpf, entrada_em, saida_em, necessidades "
              "FROM abrigados WHERE id=?")
SQL_DO_ABRIGO = ("SELECT id, abrigo_id, familia_id, nome, nome_mae, cpf, entrada_em, saida_em, necessidades "
                 "FROM abrigados WHERE abrigo_id=? AND (? = 0 OR saida_em IS NULL) ORDER BY entrada_em DESC, id")
SQL_BUSCA = (
    "SELECT p.nome, p.nome_mae, p.cpf, p.entrada_em, p.saida_em, a.id AS abrigo_id, a.nome AS abrigo_nome, "
    "a.municipio_ibge, a.gestor_id FROM abrigados p JOIN abrigos a ON a.id=p.abrigo_id "
    "WHERE p.nome_busca LIKE ? ESCAPE '\\' AND (? = 1 OR a.gestor_id = ?) "
    "ORDER BY p.saida_em IS NOT NULL, p.nome_busca, p.id LIMIT ?"
)


_APOSTROFOS = re.compile("['’‘ʼ`´]")


def nome_busca(texto: str) -> str:
    """Forma de busca, a mesma na gravação e na busca: sem acento, minúscula, espaços simples.

    Apóstrofos somem e juntam as partes ("D'Ávila" → "davila"); qualquer outra pontuação (hífen, ponto,
    vírgula, `%`, `_`...) vira espaço ("Maria-Clara  S." → "maria clara s"). Não é o `estoque.normalizar`,
    que troca apóstrofo por espaço e só guarda a-z/0-9.
    """
    s = _APOSTROFOS.sub("", texto or "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[\W_]+", " ", s).split())


def _cpf(valor: str | None, n: int) -> str | None:
    """CPF opcional: aceita pontos, hífen e espaços e guarda só os dígitos; se vier, precisa ter 11
    (não confere dígito verificador). Letra ou outro caractere → 422."""
    if valor is None:
        return None
    if re.search(r"[^0-9.\-\s]", valor):  # 0-9 e não \d: \d aceita dígitos de outras escritas
        raise HTTPException(422, f"Pessoa {n}: o CPF deve ter só números (11 dígitos)")
    digitos = re.sub(r"[^0-9]", "", valor)
    if not digitos:
        return None
    if len(digitos) != 11:
        raise HTTPException(422, f"Pessoa {n}: o CPF precisa ter 11 dígitos (ou deixe em branco)")
    return digitos


# Horário de Brasília sem horário de verão (extinto em 2019); offset fixo para não depender do tzdata no Windows.
BRASILIA = timezone(timedelta(hours=-3))


def _em_utc(iso: str) -> datetime:
    """ISO com ou sem fuso; sem fuso = horário de Brasília."""
    d = datetime.fromisoformat(iso)
    return (d if d.tzinfo else d.replace(tzinfo=BRASILIA)).astimezone(timezone.utc)


def _data(valor: str | None, campo: str) -> str:
    """Data/hora ISO guardada sempre em UTC ("2026-11-18T13:30:00+00:00"), para comparar e ordenar como texto.
    Vazio = agora; sem fuso = horário de Brasília (é o que o campo de data do navegador manda)."""
    if not valor:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        d = _em_utc(valor)
    except ValueError:
        raise HTTPException(422, f"{campo} inválida: use data e hora ISO (ex.: 2026-11-18T14:30)")
    return d.isoformat(timespec="seconds")


def _pessoa(r) -> dict:
    p = dict(r)
    p["necessidades"] = json.loads(p["necessidades"] or "[]")
    p["presente"] = p["saida_em"] is None
    return p


def contar_presentes(conn, abrigo_id: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM abrigados WHERE abrigo_id=? AND saida_em IS NULL", (abrigo_id,)).fetchone()[0]


def lotacao(conn, a: dict) -> dict:
    n, cap = contar_presentes(conn, a["id"]), a["capacidade"]
    return {"capacidade": cap, "presentes": n, "livres": max(cap - n, 0), "lotado": n >= cap, "acima": max(n - cap, 0)}


class Pessoa(BaseModel):
    nome: str = Field(max_length=200)
    nome_mae: str = Field(max_length=200)
    cpf: str | None = Field(None, max_length=30)
    necessidades: list[Literal["idoso", "deficiencia", "saude", "gestante"]] = []


class Chegada(BaseModel):
    pessoas: list[Pessoa] = Field(min_length=1, max_length=50)
    entrada_em: str | None = None


class Saida(BaseModel):
    saida_em: str | None = None


def criar_router(cfg: Config, acesso: Acesso) -> APIRouter:
    r = APIRouter()
    gestor = acesso.exige(PAPEL)

    def conectar():
        return db.conectar(cfg)

    @r.post("/abrigos/{abrigo_id}/chegadas")
    def registrar_chegada(abrigo_id: int, d: Chegada, u: dict = Depends(gestor)):
        """Uma chegada: 1 pessoa sozinha ou um grupo (2+ viram uma família). Passar da capacidade só avisa."""
        limpas = []
        for n, p in enumerate(d.pessoas, 1):
            nome, mae = " ".join(p.nome.split()), " ".join(p.nome_mae.split())
            if not nome or not mae:
                raise HTTPException(422, f"Pessoa {n}: informe o nome e o nome da mãe")
            limpas.append((nome, mae, _cpf(p.cpf, n), list(dict.fromkeys(p.necessidades))))
        entrada = _data(d.entrada_em, "Data de entrada")
        if _em_utc(entrada) > datetime.now(timezone.utc) + FOLGA_FUTURO:
            # senão a saída "agora" (padrão) ficaria antes da entrada e a pessoa não sairia mais
            raise HTTPException(422, "A data de entrada não pode estar no futuro")
        conn = conectar()
        try:
            a = abrigo_do_gestor(conn, abrigo_id, u)
            avisos = []
            cpfs = [c for _, _, c, _ in limpas if c]
            if len(cpfs) != len(set(cpfs)):
                avisos.append("O mesmo CPF aparece duas vezes nesta chegada. Confira.")
            repetidos = [c for c in set(cpfs) if conn.execute(
                "SELECT 1 FROM abrigados WHERE abrigo_id=? AND cpf=? AND saida_em IS NULL", (abrigo_id, c)).fetchone()]
            if repetidos:
                avisos.append("Já existe pessoa presente neste abrigo com o mesmo CPF. Confira se não é registro repetido.")
            familia = None
            if len(limpas) > 1:
                familia = conn.execute("INSERT INTO familias (abrigo_id) VALUES (?)", (abrigo_id,)).lastrowid
            ids = [conn.execute(
                """INSERT INTO abrigados (abrigo_id, familia_id, nome, nome_mae, cpf, nome_busca, entrada_em, necessidades)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (abrigo_id, familia, nome, mae, cpf, nome_busca(nome), entrada, json.dumps(nec))).lastrowid
                for nome, mae, cpf, nec in limpas]
            conn.commit()
            lot = lotacao(conn, a)
            if lot["acima"]:
                avisos.append(f"O abrigo passou da capacidade: {lot['presentes']} pessoas para {lot['capacidade']} vagas.")
            return {"familia_id": familia, "pessoas": [_pessoa(conn.execute(SQL_PESSOA, (i,)).fetchone()) for i in ids],
                    "lotacao": lot, "avisos": avisos}
        finally:
            conn.close()

    @r.get("/abrigos/{abrigo_id}/pessoas")
    def pessoas_abrigo(abrigo_id: int, presentes: int = 1, u: dict = Depends(gestor)):
        """Pessoas do abrigo agrupadas por família (quem chegou sozinho é um grupo de uma pessoa)."""
        conn = conectar()
        try:
            a = abrigo_do_gestor(conn, abrigo_id, u)
            grupos: dict = {}
            for linha in conn.execute(SQL_DO_ABRIGO, (abrigo_id, 1 if presentes else 0)):
                p = _pessoa(linha)
                chave = ("f", p["familia_id"]) if p["familia_id"] else ("p", p["id"])
                grupos.setdefault(chave, {"familia_id": p["familia_id"], "pessoas": []})["pessoas"].append(p)
            return {"lotacao": lotacao(conn, a), "grupos": list(grupos.values())}
        finally:
            conn.close()

    @r.get("/abrigos/{abrigo_id}/lotacao")
    def lotacao_abrigo(abrigo_id: int, u: dict = Depends(gestor)):
        conn = conectar()
        try:
            return lotacao(conn, abrigo_do_gestor(conn, abrigo_id, u))
        finally:
            conn.close()

    @r.post("/abrigados/{pessoa_id}/saida")
    def registrar_saida(pessoa_id: int, d: Saida | None = None, u: dict = Depends(gestor)):
        conn = conectar()
        try:
            linha = conn.execute(SQL_PESSOA, (pessoa_id,)).fetchone()
            if not linha:
                raise HTTPException(404, "Pessoa não encontrada")
            a = abrigo_do_gestor(conn, linha["abrigo_id"], u)  # de outro gestor → 404
            if linha["saida_em"] is not None:
                raise HTTPException(409, "A saída desta pessoa já foi registrada")
            saida = _data(d.saida_em if d else None, "Data de saída")
            if _em_utc(saida) < _em_utc(linha["entrada_em"]):
                raise HTTPException(422, "A saída não pode ser antes da entrada")
            conn.execute("UPDATE abrigados SET saida_em=? WHERE id=?", (saida, pessoa_id))
            conn.commit()
            return {"pessoa": _pessoa(conn.execute(SQL_PESSOA, (pessoa_id,)).fetchone()), "lotacao": lotacao(conn, a)}
        finally:
            conn.close()

    @r.get("/abrigados/busca")
    def buscar_abrigados(nome: str = "", u: dict = Depends(gestor)):
        """Busca por nome, sem acento e sem diferença de maiúsculas. CPF só de gente dos próprios abrigos."""
        termo = nome_busca(nome)
        if len(termo) < 2:
            raise HTTPException(422, "Digite pelo menos 2 letras do nome")
        padrao = "%" + re.sub(r"([\\%_])", r"\\\1", termo) + "%"
        conn = conectar()
        try:
            todos = gestor_verificado(conn, u["id"])
            resultados = []
            for x in conn.execute(SQL_BUSCA, (padrao, 1 if todos else 0, u["id"], LIMITE_BUSCA)):
                info = malha.carregar().info(x["municipio_ibge"]) if x["municipio_ibge"] else None
                item = {"nome": x["nome"], "nome_mae": x["nome_mae"],
                        "abrigo": {"id": x["abrigo_id"], "nome": x["abrigo_nome"], "municipio": info.get("nome") if info else None},
                        "entrada_em": x["entrada_em"], "saida_em": x["saida_em"], "presente": x["saida_em"] is None,
                        "meu_abrigo": x["gestor_id"] == u["id"]}
                if item["meu_abrigo"]:
                    item["cpf"] = x["cpf"]
                resultados.append(item)
            return {"escopo": "todos" if todos else "meus_abrigos", "resultados": resultados, "limite": LIMITE_BUSCA}
        finally:
            conn.close()

    return r
