"""Rotas /brasil/... da API (ADR 0001). Só abre o brasil.db."""
import hashlib
import json
import secrets
import string

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import campanhas, db, ingestao, inteligencia, malha, noticias
from .config import carregar

CFG = carregar()  # falha rápido na subida da API se a configuração for inválida
noticias.carregar_fontes()  # CFG-008: lista de fontes de notícia inválida também impede a subida

router = APIRouter(prefix="/brasil", tags=["brasil"])
router.include_router(campanhas.criar_router(CFG))
router.include_router(inteligencia.criar_router(CFG))
_PARAR_AUTO = ingestao.iniciar_automatico(CFG)  # FR-016; None quando BRASIL_INGESTAO_AUTO_MIN=0

USUARIOS_TESTE = {
    "voluntario": {"email": "voluntario@teste.brasil", "role": "volunteer", "name": "Voluntária de Teste",
                   "skills": ["primeiros socorros", "logística"], "lat": -30.0346, "lon": -51.2177},
    "ong": {"email": "ong@teste.brasil", "role": "org", "name": "ONG de Teste", "org_name": "ONG Brasil Solidário",
            "lat": -23.5505, "lon": -46.6333},
    "admin": {"email": "admin@teste.brasil", "role": "admin", "name": "Admin de Teste", "lat": -15.7939, "lon": -47.8828},
}

CAMPOS_USUARIO = "id, email, role, name, phone, skills, languages, lat, lon, radius_km, org_name, available, link_code"


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()  # mesmo formato do Crisis, para o merge (ADR 0002)


def _link_code() -> str:
    raw = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    return raw[:4] + "-" + raw[4:]


def _usuario(conn, uid: int) -> dict:
    r = conn.execute(f"SELECT {CAMPOS_USUARIO} FROM users WHERE id=?", (uid,)).fetchone()
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
def obter_usuario(uid: int):
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
def atualizar_usuario(uid: int, p: Perfil):
    """FR-010: a localização precisa estar dentro do Brasil."""
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
            conn.execute(f"UPDATE users SET {', '.join(f'{k}=?' for k in dados)} WHERE id=?", (*dados.values(), uid))
            conn.commit()
        return _usuario(conn, uid)
    finally:
        conn.close()


# ── crises ────────────────────────────────────────────────────────────
@router.get("/crises")
def listar_crises():
    return ingestao.crises_ativas(CFG)


@router.get("/voluntarios/por-municipio")
def voluntarios_por_municipio():
    """FR-007: voluntários disponíveis por município (localização do perfil)."""
    m = malha.carregar()
    conn = db.conectar(CFG)
    try:
        linhas = conn.execute("SELECT lat, lon FROM users WHERE role='volunteer' AND available=1").fetchall()
    finally:
        conn.close()
    contagem: dict[int, int] = {}
    for r in linhas:
        cod = m.municipio_em(r["lat"], r["lon"]) if r["lat"] is not None else None
        if cod:
            contagem[cod] = contagem.get(cod, 0) + 1
    return contagem


class Inscricao(BaseModel):
    user_id: int


@router.post("/crises/{crisis_id}/inscrever")
def inscrever(crisis_id: str, d: Inscricao):
    """FR-009: voluntário ou ONG se inscreve numa crise BR."""
    conn = db.conectar(CFG)
    try:
        u = _usuario(conn, d.user_id)
        if u["role"] not in ("volunteer", "org"):
            raise HTTPException(403, "Só voluntários e ONGs se inscrevem em crises")
        if not conn.execute("SELECT 1 FROM crises WHERE id=?", (crisis_id,)).fetchone():
            raise HTTPException(404, "Crise não encontrada")
        conn.execute("INSERT OR IGNORE INTO crisis_associations (crisis_id, user_id, role) VALUES (?,?,?)",
                     (crisis_id, d.user_id, u["role"]))
        conn.commit()
        return {"ok": True, "inscritos": conn.execute(
            "SELECT COUNT(*) FROM crisis_associations WHERE crisis_id=?", (crisis_id,)).fetchone()[0]}
    finally:
        conn.close()


@router.post("/crises/{crisis_id}/cancelar")
def cancelar(crisis_id: str, d: Inscricao):
    conn = db.conectar(CFG)
    try:
        conn.execute("DELETE FROM crisis_associations WHERE crisis_id=? AND user_id=?", (crisis_id, d.user_id))
        conn.commit()
        return {"ok": True, "inscritos": conn.execute(
            "SELECT COUNT(*) FROM crisis_associations WHERE crisis_id=?", (crisis_id,)).fetchone()[0]}
    finally:
        conn.close()


@router.get("/usuarios/{uid}/inscricoes")
def inscricoes(uid: int):
    conn = db.conectar(CFG)
    try:
        return [dict(r) for r in conn.execute(
            """SELECT c.id, c.title, c.severity, c.crisis_type, c.uf, a.created_at
               FROM crisis_associations a JOIN crises c ON c.id=a.crisis_id WHERE a.user_id=? ORDER BY a.created_at DESC""",
            (uid,))]
    finally:
        conn.close()


# ── ingestão ──────────────────────────────────────────────────────────
@router.get("/ingestao/status")
def status_ingestao():
    return ingestao.status(CFG)
