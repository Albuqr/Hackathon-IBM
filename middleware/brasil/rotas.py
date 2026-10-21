"""Rotas /brasil/... da API (ADR 0001). Só abre o brasil.db."""
import hashlib
import json
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import campanhas, db, ingestao, inteligencia, malha, noticias
from .acesso import Acesso
from .config import carregar

CFG = carregar()  # falha rápido na subida da API se a configuração for inválida
noticias.carregar_fontes()  # CFG-008: lista de fontes de notícia inválida também impede a subida

ACESSO = Acesso(CFG)
router = APIRouter(prefix="/brasil", tags=["brasil"])
router.include_router(campanhas.criar_router(CFG, ACESSO))
router.include_router(inteligencia.criar_router(CFG, ACESSO))
_PARAR_AUTO = ingestao.iniciar_automatico(CFG)  # FR-016; None quando BRASIL_INGESTAO_AUTO_MIN=0

USUARIOS_TESTE = {
    "voluntario": {"email": "voluntario@teste.brasil", "role": "volunteer", "name": "Voluntária de Teste",
                   "skills": ["primeiros socorros", "logística"], "lat": -30.0346, "lon": -51.2177},
    "ong": {"email": "ong@teste.brasil", "role": "org", "name": "ONG de Teste", "org_name": "ONG Brasil Solidário",
            "lat": -23.5505, "lon": -46.6333},
    "admin": {"email": "admin@teste.brasil", "role": "admin", "name": "Admin de Teste", "lat": -15.7939, "lon": -47.8828},
}

SQL_USUARIO = (
    "SELECT id, email, role, name, phone, skills, languages, lat, lon, radius_km, org_name, "
    "available, link_code FROM users WHERE id=?"
)
# One literal statement per editable field, so no SQL is built from strings.
ATUALIZAR_USUARIO = {
    "name": "UPDATE users SET name=? WHERE id=?",
    "phone": "UPDATE users SET phone=? WHERE id=?",
    "skills": "UPDATE users SET skills=? WHERE id=?",
    "languages": "UPDATE users SET languages=? WHERE id=?",
    "lat": "UPDATE users SET lat=? WHERE id=?",
    "lon": "UPDATE users SET lon=? WHERE id=?",
    "radius_km": "UPDATE users SET radius_km=? WHERE id=?",
    "available": "UPDATE users SET available=? WHERE id=?",
}


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()  # mesmo formato do Crisis, para o merge (ADR 0002)


def _link_code() -> str:
    raw = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    return raw[:4] + "-" + raw[4:]


def _usuario(conn, uid: int) -> dict:
    r = conn.execute(SQL_USUARIO, (uid,)).fetchone()
    if not r:
        raise HTTPException(404, "Usuário não encontrado")
    u = dict(r)
    for k in ("skills", "languages"):
        u[k] = json.loads(u[k] or "[]")
    return u


@router.get("/saude")
def saude():
    return {"ok": True, "orquestrador": CFG.orquestrador, "notificacoes": CFG.notificacoes}


@router.get("/malha")
def obter_malha():
    return FileResponse(malha.ARQUIVO, media_type="application/json")


# ── usuários e login ──────────────────────────────────────────────────
class Login(BaseModel):
    email: str
    senha: str


@router.post("/login")
def login(d: Login):
    conn = db.conectar(CFG)
    try:
        r = conn.execute("SELECT id FROM users WHERE email=? AND password_hash=?", (d.email.strip().lower(), _hash(d.senha))).fetchone()
        if not r:
            raise HTTPException(401, "E-mail ou senha inválidos")
        return _usuario(conn, r["id"])
    finally:
        conn.close()


@router.post("/dev/usuario/{perfil}")
def dev_usuario(perfil: str):
    """FR-005: cria (se preciso) e devolve o usuário de teste do perfil. Só com BRASIL_DEV_LOGIN=1."""
    if not CFG.dev_login or perfil not in USUARIOS_TESTE:
        raise HTTPException(404, "Não encontrado")
    t = USUARIOS_TESTE[perfil]
    conn = db.conectar(CFG)
    try:
        r = conn.execute("SELECT id FROM users WHERE email=?", (t["email"],)).fetchone()
        if r:
            uid = r["id"]
        else:
            cur = conn.execute(
                """INSERT INTO users (email, password_hash, role, name, skills, lat, lon, radius_km, org_name, link_code)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (t["email"], _hash(secrets.token_hex(16)), t["role"], t["name"], json.dumps(t.get("skills", [])),
                 t["lat"], t["lon"], 300, t.get("org_name"), _link_code() if t["role"] == "volunteer" else None),
            )
            conn.commit()
            uid = cur.lastrowid
        return _usuario(conn, uid)
    finally:
        conn.close()


@router.get("/usuarios/{uid}")
def obter_usuario(uid: int, u: dict = Depends(ACESSO.identidade)):
    ACESSO.proprio(u, uid)
    conn = db.conectar(CFG)
    try:
        return _usuario(conn, uid)
    finally:
        conn.close()


class Perfil(BaseModel):
    name: str | None = None
    phone: str | None = None
    skills: list[str] | None = None
    languages: list[str] | None = None
    lat: float | None = None
    lon: float | None = None
    radius_km: float | None = None
    available: bool | None = None


@router.put("/usuarios/{uid}")
def atualizar_usuario(uid: int, p: Perfil, u: dict = Depends(ACESSO.identidade)):
    """FR-010: a localização precisa estar dentro do Brasil."""
    ACESSO.proprio(u, uid)
    dados = p.model_dump(exclude_none=True)
    if ("lat" in dados) != ("lon" in dados):
        raise HTTPException(422, "Informe latitude e longitude juntas")
    if "lat" in dados and not malha.carregar().no_brasil(dados["lat"], dados["lon"]):
        raise HTTPException(422, "A localização precisa estar no Brasil")
    if "radius_km" in dados and not (1 <= dados["radius_km"] <= 5000):
        raise HTTPException(422, "O raio precisa estar entre 1 e 5000 km")
    for k in ("skills", "languages"):
        if k in dados:
            dados[k] = json.dumps([s.strip() for s in dados[k] if s.strip()], ensure_ascii=False)
    conn = db.conectar(CFG)
    try:
        _usuario(conn, uid)
        if dados:
            for campo, valor in dados.items():
                conn.execute(ATUALIZAR_USUARIO[campo], (valor, uid))
            conn.commit()
        return _usuario(conn, uid)
    finally:
        conn.close()


# ── crises ────────────────────────────────────────────────────────────
@router.get("/crises")
def listar_crises(sev_min: float = 0, uf: str = "", tipo: str = "", fonte: str = "", verificacao: str = "",
                  q: str = "", limite: int = 0):
    """FR-022: mesmos filtros do mapa; UF = qualquer município da crise na UF (FR-009)."""
    return ingestao.filtrar(ingestao.crises_ativas(CFG), sev_min=sev_min, uf=uf, tipo=tipo, fonte=fonte,
                            verificacao=verificacao, q=q, limite=limite)


@router.post("/crises/{crisis_id}/inscrever")
def inscrever(crisis_id: str, u: dict = Depends(ACESSO.exige("volunteer", "org"))):
    """FR-009: voluntário ou ONG se inscreve numa crise BR."""
    conn = db.conectar(CFG)
    try:
        if not conn.execute("SELECT 1 FROM crises WHERE id=?", (crisis_id,)).fetchone():
            raise HTTPException(404, "Crise não encontrada")
        conn.execute("INSERT OR IGNORE INTO crisis_associations (crisis_id, user_id, role) VALUES (?,?,?)",
                     (crisis_id, u["id"], u["role"]))
        conn.commit()
        return {"ok": True, **ingestao.associados(conn, crisis_id)}
    finally:
        conn.close()


@router.post("/crises/{crisis_id}/cancelar")
def cancelar(crisis_id: str, u: dict = Depends(ACESSO.exige("volunteer", "org"))):
    conn = db.conectar(CFG)
    try:
        conn.execute("DELETE FROM crisis_associations WHERE crisis_id=? AND user_id=?", (crisis_id, u["id"]))
        conn.commit()
        return {"ok": True, **ingestao.associados(conn, crisis_id)}
    finally:
        conn.close()


@router.get("/usuarios/{uid}/inscricoes")
def inscricoes(uid: int, u: dict = Depends(ACESSO.identidade)):
    ACESSO.proprio(u, uid)
    conn = db.conectar(CFG)
    try:
        return [dict(r) for r in conn.execute(
            """SELECT c.id, c.title, c.severity, c.crisis_type, c.uf, c.lat, c.lon, a.created_at
               FROM crisis_associations a JOIN crises c ON c.id=a.crisis_id WHERE a.user_id=? ORDER BY a.created_at DESC""",
            (uid,))]
    finally:
        conn.close()


# ── ingestão ──────────────────────────────────────────────────────────
@router.get("/ingestao/status")
def status_ingestao():
    return ingestao.status(CFG)
