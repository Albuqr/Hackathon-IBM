"""Campanhas, convites e painel da ONG no Dash Brasil (FR-011–FR-014).

Mesma semântica das rotas /campaigns do Crisis, sobre o brasil.db, com checagem de dono:
a ONG só mexe nas próprias campanhas, o voluntário só responde aos próprios convites.
"""
import json
import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import assistentes, db, notificacoes
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
    convidados: list[int] = []  # publicar e convidar numa chamada só


# One literal statement per editable field, so no SQL is built from strings.
ATUALIZAR_CAMPANHA = {
    "title": "UPDATE campaigns SET title=? WHERE id=?",
    "description": "UPDATE campaigns SET description=? WHERE id=?",
    "skills_needed": "UPDATE campaigns SET skills_needed=? WHERE id=?",
    "target_volunteers": "UPDATE campaigns SET target_volunteers=? WHERE id=?",
    "start_date": "UPDATE campaigns SET start_date=? WHERE id=?",
    "end_date": "UPDATE campaigns SET end_date=? WHERE id=?",
    "urgency": "UPDATE campaigns SET urgency=? WHERE id=?",
    "status": "UPDATE campaigns SET status=? WHERE id=?",
}
VOLUNTARIOS_BASE = (
    "SELECT id, name, email, skills, lat, lon, radius_km, available FROM users "
    "WHERE role='volunteer' AND lat!=0 AND lon!=0"
)
VOLUNTARIOS_DISPONIVEIS = (
    "SELECT id, name, email, skills, lat, lon, radius_km, available FROM users "
    "WHERE role='volunteer' AND lat!=0 AND lon!=0 AND available=1"
)


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


class Convites(BaseModel):
    volunteer_ids: list[int] = Field(min_length=1, max_length=200)
    reenviar: bool = False


class PreviaConvite(BaseModel):
    crisis_id: str
    title: str = ""
    urgency: str = "media"
    skills_needed: list[str] = []
    volunteer_id: int | None = None


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

    def org_nome(conn, org_id: int) -> str:
        r = conn.execute("SELECT COALESCE(org_name, name) FROM users WHERE id=?", (org_id,)).fetchone()
        return r[0] if r and r[0] else "ONG"

    def crise_de(conn, crisis_id: str) -> dict:
        c = conn.execute("SELECT * FROM crises WHERE id=?", (crisis_id,)).fetchone()
        return dict(c) if c else {"id": crisis_id, "title": "Crise", "lat": None, "lon": None, "severity": 0}

    def convidar(conn, cid: int, ids: list[int], reenviar: bool = False) -> dict:
        """Grava os convites e manda a mensagem da campanha (fila ou Telegram). Quem já está na campanha é pulado;
        `reenviar` só alcança quem ainda não respondeu e renova a data do convite."""
        cam = campanha_completa(conn, cid)
        agora = datetime.now(timezone.utc).isoformat()
        alvo = []
        for vid in dict.fromkeys(ids):
            v = conn.execute("SELECT id, name, role, lat, lon, telegram_id, phone FROM users WHERE id=?", (vid,)).fetchone()
            if not v or v["role"] != "volunteer":
                continue
            atual = conn.execute("SELECT status FROM campaign_volunteers WHERE campaign_id=? AND volunteer_id=?", (cid, vid)).fetchone()
            if reenviar:
                if not atual or atual["status"] != "selected":
                    continue
                conn.execute("UPDATE campaign_volunteers SET added_at=? WHERE campaign_id=? AND volunteer_id=?", (agora, cid, vid))
            else:
                if atual and atual["status"] in ("selected", "confirmed"):
                    continue
                conn.execute(
                    """INSERT INTO campaign_volunteers (campaign_id, volunteer_id, status, added_at) VALUES (?,?,'selected',?)
                       ON CONFLICT(campaign_id, volunteer_id) DO UPDATE SET status='selected', added_at=excluded.added_at""",
                    (cid, vid, agora))
            alvo.append({"volunteer_id": v["id"], "name": v["name"], "lat": v["lat"], "lon": v["lon"],
                         "telegram_id": v["telegram_id"], "phone": v["phone"]})
        rel = notificacoes.convidar(cfg, conn, cam, crise_de(conn, cam["crisis_id"]), org_nome(conn, cam["org_id"]), alvo)
        return {"convidados": len(alvo), **rel}

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
            convites = convidar(conn, cur.lastrowid, c.convidados) if c.convidados else None
            conn.commit()
            return campanha_completa(conn, cur.lastrowid) | {"convites": convites}
        finally:
            conn.close()

    @r.get("/campanhas")
    def listar(org_id: int | None = None, u: dict = Depends(ong_ou_admin)):
        if u["role"] == "org":
            org_id = u["id"]  # a ONG só vê as próprias
        conn = conectar()
        try:
            if org_id is not None:
                linhas = conn.execute("SELECT id FROM campaigns WHERE org_id=? ORDER BY created_at DESC", (org_id,))
            else:
                linhas = conn.execute("SELECT id FROM campaigns ORDER BY created_at DESC")
            return [campanha_completa(conn, row["id"]) for row in linhas]
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
            antes = dono(conn, cid, u)
            dados = e.model_dump(exclude_none=True)
            if "skills_needed" in dados:
                dados["skills_needed"] = json.dumps([s.strip() for s in dados["skills_needed"] if s.strip()], ensure_ascii=False)
            for campo, valor in dados.items():
                conn.execute(ATUALIZAR_CAMPANHA[campo], (valor, cid))
            if dados.get("status") == "closed" and antes["status"] == "active":  # avisa os confirmados
                conf = [dict(x) for x in conn.execute(
                    """SELECT u.id AS volunteer_id, u.name, u.telegram_id, u.phone FROM campaign_volunteers cv
                       JOIN users u ON u.id=cv.volunteer_id WHERE cv.campaign_id=? AND cv.status='confirmed'""", (cid,))]
                notificacoes.avisar_encerramento(cfg, conn, antes, org_nome(conn, antes["org_id"]), conf)
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
            rel = convidar(conn, cid, [a.volunteer_id])
            conn.commit()
            return {"ok": True, **rel}
        finally:
            conn.close()

    @r.post("/campanhas/{cid}/convites")
    def convidar_varios(cid: int, c: Convites, u: dict = Depends(ong_ou_admin)):
        """Convida (ou lembra quem não respondeu) vários voluntários; cada um recebe a mensagem da campanha."""
        conn = conectar()
        try:
            if dono(conn, cid, u)["status"] != "active":
                raise HTTPException(409, "A campanha está encerrada")
            rel = convidar(conn, cid, c.volunteer_ids, c.reenviar)
            conn.commit()
            return rel
        finally:
            conn.close()

    @r.get("/campanhas/{cid}/situacao")
    def situacao(cid: int, u: dict = Depends(ong_ou_admin)):
        """Próximo passo, funil de convites, cobertura do plano e recomendados (regras determinísticas)."""
        conn = conectar()
        try:
            dono(conn, cid, u)
        finally:
            conn.close()
        return assistentes.situacao_campanha(cfg, cid)

    @r.post("/convites/previa")
    def previa(p: PreviaConvite, u: dict = Depends(ong)):
        """O texto exato que o voluntário recebe, para a ONG revisar antes de publicar."""
        conn = conectar()
        try:
            crise = crise_de(conn, p.crisis_id)
            v = conn.execute("SELECT name, lat, lon FROM users WHERE id=? AND role='volunteer'", (p.volunteer_id,)).fetchone() \
                if p.volunteer_id else None
            km = assistentes.haversine_km(crise["lat"], crise["lon"], v["lat"], v["lon"]) \
                if v and v["lat"] and crise.get("lat") is not None else None
            texto = notificacoes.mensagem_convite(v["name"] if v else "voluntário", org_nome(conn, u["id"]),
                                                  p.model_dump(), crise, km)
            return {"texto": texto, "canal": cfg.notificacoes}
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
            for u in conn.execute(VOLUNTARIOS_BASE if incluir_indisponiveis else VOLUNTARIOS_DISPONIVEIS):
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
            org = conn.execute("SELECT lat, lon FROM users WHERE id=?", (org_id,)).fetchone()
            disponiveis = conn.execute(
                """SELECT COUNT(DISTINCT u.id) FROM campaign_volunteers cv JOIN campaigns cam ON cam.id=cv.campaign_id
                   JOIN users u ON u.id=cv.volunteer_id WHERE cam.org_id=? AND cv.status IN ('selected','confirmed')
                   AND u.available=1""", (org_id,)).fetchone()[0]
        finally:
            conn.close()
        # o que pede ação primeiro: o próximo passo de cada campanha ativa e as crises sem gente perto da ONG
        for c in campanhas:
            if c["status"] == "active":
                c["proximo_passo"] = assistentes.situacao_campanha(cfg, c["id"])["proximo_passo"]
        minhas = {c["crisis_id"] for c in campanhas if c["status"] == "active"}
        lacunas = [l for l in assistentes.distribuicao(cfg)["lacunas"] if l["crisis_id"] not in minhas]
        for l in lacunas:
            l["distancia_km"] = round(assistentes.haversine_km(org["lat"], org["lon"], l["lat"], l["lon"])) if org and org["lat"] else None
        lacunas.sort(key=lambda l: (l["distancia_km"] is None, l["distancia_km"] or 0, -l["severity"]))
        return {
            "lacunas_perto": lacunas[:5],
            "voluntarios_selecionados": sum(c["selecionados"] for c in campanhas),
            "campanhas_ativas": sum(1 for c in campanhas if c["status"] == "active"),
            # voluntários distintos nas campanhas desta ONG e, deles, os disponíveis (AC-017.1)
            "voluntarios": len(vols),
            "voluntarios_disponiveis": disponiveis,
            "crises_apoiadas": len(crises),
            "habilidades": dict(sorted(habilidades.items(), key=lambda kv: -kv[1])),
            "campanhas": campanhas,
            "crescimento": crescimento,
        }

    return r
