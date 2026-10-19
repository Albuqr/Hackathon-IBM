"""Campanhas, convites e painel da ONG no Dash Brasil (FR-011–FR-014).

Mesma semântica das rotas /campaigns do Crisis, sobre o brasil.db, com checagem de dono:
a ONG só mexe nas próprias campanhas, o voluntário só responde aos próprios convites.
"""
import json
import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .acesso import Acesso
from .config import Config

URGENCIAS = ("baixa", "media", "alta", "critica")


def _haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class NovaCampanha(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = ""
    crisis_id: str
    skills_needed: list[str] = []
    target_volunteers: int = Field(10, ge=1, le=10000)
    start_date: str = ""
    end_date: str = ""
    urgency: str = "media"


class EdicaoCampanha(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=200)
    description: str | None = None
    skills_needed: list[str] | None = None
    target_volunteers: int | None = Field(None, ge=1, le=10000)
    start_date: str | None = None
    end_date: str | None = None
    urgency: str | None = None
    status: str | None = None


class AdicionarVoluntario(BaseModel):
    volunteer_id: int


class RespostaConvite(BaseModel):
    status: str


def criar_router(cfg: Config, acesso: Acesso) -> APIRouter:
    r = APIRouter()
    ong = acesso.exige("org")
    ong_ou_admin = acesso.exige("org", "admin")

    def conectar():
        return db.conectar(cfg)

    def dono(conn, campanha_id: int, u: dict) -> dict:
        """A ONG dona da campanha (o admin também passa)."""
        c = conn.execute("SELECT * FROM campaigns WHERE id=?", (campanha_id,)).fetchone()
        if not c:
            raise HTTPException(404, "Campanha não encontrada")
        if c["org_id"] != u["id"] and u["role"] != "admin":
            raise HTTPException(403, "Esta campanha é de outra ONG")
        return dict(c)

    def exige_ong(conn, org_id: int):
        u = conn.execute("SELECT role FROM users WHERE id=?", (org_id,)).fetchone()
        if not u or u["role"] != "org":
            raise HTTPException(403, "Só ONGs gerenciam campanhas")

    def campanha_completa(conn, cid: int) -> dict:
        c = conn.execute(
            """SELECT cam.*, c.title AS crisis_title, c.severity AS crisis_severity, c.uf AS crisis_uf,
                      c.crisis_type AS crisis_type, c.lat AS crisis_lat, c.lon AS crisis_lon,
                      (SELECT COUNT(*) FROM campaign_volunteers cv WHERE cv.campaign_id=cam.id
                         AND cv.status IN ('selected','confirmed')) AS selecionados,
                      (SELECT COUNT(*) FROM campaign_volunteers cv WHERE cv.campaign_id=cam.id
                         AND cv.status='confirmed') AS confirmados
               FROM campaigns cam LEFT JOIN crises c ON c.id=cam.crisis_id WHERE cam.id=?""", (cid,)).fetchone()
        d = dict(c)
        d["skills_needed"] = json.loads(d["skills_needed"] or "[]")
        return d

    # ── ONG: campanhas ────────────────────────────────────────────────
    @r.post("/campanhas")
    def criar(c: NovaCampanha, u: dict = Depends(ong)):
        if c.urgency not in URGENCIAS:
            raise HTTPException(422, f"Urgência inválida; use {', '.join(URGENCIAS)}")
        conn = conectar()
        try:
            if not conn.execute("SELECT 1 FROM crises WHERE id=?", (c.crisis_id,)).fetchone():
                raise HTTPException(422, "Escolha uma crise do Brasil que esteja no mapa")
            cur = conn.execute(
                """INSERT INTO campaigns (org_id, title, description, crisis_id, skills_needed, target_volunteers,
                       start_date, end_date, urgency, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,'active',?)""",
                (u["id"], c.title.strip(), c.description, c.crisis_id,
                 json.dumps([s.strip() for s in c.skills_needed if s.strip()], ensure_ascii=False),
                 c.target_volunteers, c.start_date, c.end_date, c.urgency, datetime.now(timezone.utc).isoformat()))
            conn.commit()
            return campanha_completa(conn, cur.lastrowid)
        finally:
            conn.close()

    @r.get("/campanhas")
    def listar(org_id: int | None = None, u: dict = Depends(ong_ou_admin)):
        if u["role"] == "org":
            org_id = u["id"]  # a ONG só vê as próprias
        conn = conectar()
        try:
            q, p = "SELECT id FROM campaigns", ()
            if org_id is not None:
                q, p = q + " WHERE org_id=?", (org_id,)
            return [campanha_completa(conn, row["id"]) for row in conn.execute(q + " ORDER BY created_at DESC", p)]
        finally:
            conn.close()

    @r.get("/campanhas/{cid}")
    def obter(cid: int, u: dict = Depends(ong_ou_admin)):
        conn = conectar()
        try:
            dono(conn, cid, u)
            return campanha_completa(conn, cid)
        finally:
            conn.close()

    @r.put("/campanhas/{cid}")
    def editar(cid: int, e: EdicaoCampanha, u: dict = Depends(ong_ou_admin)):
        if e.urgency is not None and e.urgency not in URGENCIAS:
            raise HTTPException(422, f"Urgência inválida; use {', '.join(URGENCIAS)}")
        if e.status is not None and e.status not in ("active", "closed"):
            raise HTTPException(422, "Status inválido; use active ou closed")
        conn = conectar()
        try:
            dono(conn, cid, u)
            dados = e.model_dump(exclude_none=True)
            if "skills_needed" in dados:
                dados["skills_needed"] = json.dumps([s.strip() for s in dados["skills_needed"] if s.strip()], ensure_ascii=False)
            if dados:
                conn.execute(f"UPDATE campaigns SET {', '.join(f'{k}=?' for k in dados)} WHERE id=?", (*dados.values(), cid))
                conn.commit()
            return campanha_completa(conn, cid)
        finally:
            conn.close()

    # ── ONG: voluntários da campanha ──────────────────────────────────
    @r.get("/campanhas/{cid}/voluntarios")
    def voluntarios_da_campanha(cid: int, u: dict = Depends(ong_ou_admin)):
        conn = conectar()
        try:
            dono(conn, cid, u)
            return [dict(x) | {"skills": json.loads(x["skills"] or "[]")} for x in conn.execute(
                """SELECT cv.id AS cv_id, cv.volunteer_id, cv.status, cv.added_at, u.name, u.email, u.skills, u.lat, u.lon
                   FROM campaign_volunteers cv JOIN users u ON u.id=cv.volunteer_id
                   WHERE cv.campaign_id=? AND cv.status != 'removed' ORDER BY cv.added_at DESC""", (cid,))]
        finally:
            conn.close()

    @r.post("/campanhas/{cid}/voluntarios")
    def adicionar(cid: int, a: AdicionarVoluntario, u: dict = Depends(ong_ou_admin)):
        conn = conectar()
        try:
            c = dono(conn, cid, u)
            if c["status"] != "active":
                raise HTTPException(409, "A campanha está encerrada")
            v = conn.execute("SELECT role FROM users WHERE id=?", (a.volunteer_id,)).fetchone()
            if not v or v["role"] != "volunteer":
                raise HTTPException(404, "Voluntário não encontrado")
            conn.execute(
                """INSERT INTO campaign_volunteers (campaign_id, volunteer_id, status, added_at) VALUES (?,?,'selected',?)
                   ON CONFLICT(campaign_id, volunteer_id) DO UPDATE SET status='selected', added_at=excluded.added_at""",
                (cid, a.volunteer_id, datetime.now(timezone.utc).isoformat()))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    @r.delete("/campanhas/{cid}/voluntarios/{vid}")
    def remover(cid: int, vid: int, u: dict = Depends(ong_ou_admin)):
        conn = conectar()
        try:
            dono(conn, cid, u)
            conn.execute("UPDATE campaign_volunteers SET status='removed' WHERE campaign_id=? AND volunteer_id=?", (cid, vid))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    @r.get("/voluntarios/disponiveis")
    def disponiveis(crisis_id: str | None = None, raio_km: float = 1000, incluir_indisponiveis: bool = False,
                    u: dict = Depends(ong_ou_admin)):
        """Voluntários no Brasil (só os disponíveis, salvo incluir_indisponiveis); com crise, filtra pelo raio
        e ordena por distância."""
        conn = conectar()
        try:
            alvo = conn.execute("SELECT lat, lon FROM crises WHERE id=?", (crisis_id,)).fetchone() if crisis_id else None
            out = []
            filtro = "" if incluir_indisponiveis else " AND available=1"
            for u in conn.execute("SELECT id, name, email, skills, lat, lon, radius_km, available FROM users "
                                  "WHERE role='volunteer' AND lat!=0 AND lon!=0" + filtro):
                d = dict(u) | {"skills": json.loads(u["skills"] or "[]"), "distancia_km": None}
                if alvo:
                    d["distancia_km"] = round(_haversine_km(alvo["lat"], alvo["lon"], u["lat"], u["lon"]), 1)
                    if d["distancia_km"] > raio_km:
                        continue
                out.append(d)
            return sorted(out, key=lambda d: d["distancia_km"] if d["distancia_km"] is not None else 0)
        finally:
            conn.close()

    # ── voluntário: convites ──────────────────────────────────────────
    @r.get("/voluntario/{uid}/campanhas")
    def campanhas_do_voluntario(uid: int, u: dict = Depends(acesso.identidade)):
        acesso.proprio(u, uid)
        conn = conectar()
        try:
            return [dict(x) for x in conn.execute(
                """SELECT cv.id AS cv_id, cv.campaign_id, cv.status, cv.added_at, cam.title, cam.description,
                          cam.urgency, cam.target_volunteers, c.title AS crisis_title, c.severity AS crisis_severity,
                          c.uf AS crisis_uf, COALESCE(o.org_name, o.name) AS org_name
                   FROM campaign_volunteers cv JOIN campaigns cam ON cam.id=cv.campaign_id
                   LEFT JOIN crises c ON c.id=cam.crisis_id LEFT JOIN users o ON o.id=cam.org_id
                   WHERE cv.volunteer_id=? AND cv.status NOT IN ('removed') ORDER BY cv.added_at DESC""", (uid,))]
        finally:
            conn.close()

    @r.put("/convites/{cv_id}")
    def responder(cv_id: int, resp: RespostaConvite, u: dict = Depends(acesso.exige("volunteer"))):
        if resp.status not in ("confirmed", "declined"):
            raise HTTPException(422, "Responda com confirmed ou declined")
        conn = conectar()
        try:
            cv = conn.execute("SELECT volunteer_id, status FROM campaign_volunteers WHERE id=?", (cv_id,)).fetchone()
            if not cv or cv["status"] == "removed":
                raise HTTPException(404, "Convite não encontrado")
            if cv["volunteer_id"] != u["id"]:
                raise HTTPException(403, "Este convite é de outro voluntário")
            conn.execute("UPDATE campaign_volunteers SET status=? WHERE id=?", (resp.status, cv_id))
            conn.commit()
            return {"ok": True, "status": resp.status}
        finally:
            conn.close()

    # ── painel da ONG ─────────────────────────────────────────────────
    @r.get("/ong/{org_id}/painel")
    def painel(org_id: int, u: dict = Depends(ong_ou_admin)):
        acesso.proprio(u, org_id)
        conn = conectar()
        try:
            exige_ong(conn, org_id)
            campanhas = [campanha_completa(conn, x["id"]) for x in
                         conn.execute("SELECT id FROM campaigns WHERE org_id=? ORDER BY created_at DESC", (org_id,))]
            vols = conn.execute(
                """SELECT DISTINCT u.id, u.skills FROM campaign_volunteers cv JOIN campaigns cam ON cam.id=cv.campaign_id
                   JOIN users u ON u.id=cv.volunteer_id WHERE cam.org_id=? AND cv.status IN ('selected','confirmed')""",
                (org_id,)).fetchall()
            habilidades: dict[str, int] = {}
            for v in vols:
                for s in json.loads(v["skills"] or "[]"):
                    habilidades[s] = habilidades.get(s, 0) + 1
            crises = {c["crisis_id"] for c in campanhas if c["crisis_id"]} | {
                x["crisis_id"] for x in conn.execute("SELECT crisis_id FROM crisis_associations WHERE user_id=?", (org_id,))}
            hoje = datetime.now(timezone.utc).date()
            dias = [(hoje - timedelta(days=6 - i)).isoformat() for i in range(7)]
            crescimento = {}
            for c in campanhas:
                cont = dict(conn.execute(
                    """SELECT substr(added_at, 1, 10), COUNT(*) FROM campaign_volunteers
                       WHERE campaign_id=? AND status IN ('selected','confirmed') AND substr(added_at, 1, 10) >= ?
                       GROUP BY 1""", (c["id"], dias[0])).fetchall())
                crescimento[c["id"]] = [{"dia": d, "n": cont.get(d, 0)} for d in dias]
            return {
                "voluntarios_selecionados": sum(c["selecionados"] for c in campanhas),
                "campanhas_ativas": sum(1 for c in campanhas if c["status"] == "active"),
                # voluntários distintos nas campanhas desta ONG e, deles, os disponíveis (AC-017.1)
                "voluntarios": len(vols),
                "voluntarios_disponiveis": conn.execute(
                    """SELECT COUNT(DISTINCT u.id) FROM campaign_volunteers cv JOIN campaigns cam ON cam.id=cv.campaign_id
                       JOIN users u ON u.id=cv.volunteer_id WHERE cam.org_id=? AND cv.status IN ('selected','confirmed')
                       AND u.available=1""", (org_id,)).fetchone()[0],
                "crises_apoiadas": len(crises),
                "habilidades": dict(sorted(habilidades.items(), key=lambda kv: -kv[1])),
                "campanhas": campanhas,
                "crescimento": crescimento,
            }
        finally:
            conn.close()

    return r
