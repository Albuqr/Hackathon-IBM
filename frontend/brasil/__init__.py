"""Dash Brasil — páginas /brasil/... do frontend do Crisis Monitor (ADR 0001).

Fala só com a API /brasil/... (nunca abre banco). A sessão usa chaves próprias
(br_user_id, br_role, br_nome) porque os IDs vêm do brasil.db, não do banco do Crisis.
"""
import os
from functools import wraps

import requests
from token_api import cabecalhos  # segredo da API (ADR 0004)
from flask import Blueprint, Response, abort, jsonify, redirect, render_template, request, session, url_for

API = os.environ.get("API_URL", "http://localhost:8000")
PERFIS = {"voluntario": "volunteer", "ong": "org", "admin": "admin"}
NOME_PAPEL = {"volunteer": "Voluntário", "org": "ONG", "admin": "Admin"}

bp = Blueprint("brasil", __name__, url_prefix="/brasil",
               template_folder="templates", static_folder="static", static_url_path="/static")

_malha_cache: dict = {}


def dev_login_ligado() -> bool:
    return os.environ.get("BRASIL_DEV_LOGIN", "") == "1"


def api(metodo: str, caminho: str, timeout=30, **kw):
    """Chama a API /brasil; devolve (status, json)."""
    try:
        r = requests.request(metodo, f"{API}/brasil{caminho}", timeout=timeout, headers=cabecalhos(), **kw)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {}
    except requests.RequestException as e:
        return 503, {"detail": f"API indisponível: {e}"}


def exige_login(*papeis):
    def deco(f):
        @wraps(f)
        def w(*a, **kw):
            if "br_user_id" not in session:
                return redirect(url_for("brasil.entrar"))
            if papeis and session.get("br_role") not in papeis:
                abort(403)
            return f(*a, **kw)
        return w
    return deco


def _entrar(usuario: dict):
    session["br_user_id"] = usuario["id"]
    session["br_role"] = usuario["role"]
    session["br_nome"] = usuario.get("org_name") or usuario.get("name") or usuario["email"]


@bp.context_processor
def contexto():
    return {"br_nome": session.get("br_nome"), "br_role": session.get("br_role"),
            "br_papel": NOME_PAPEL.get(session.get("br_role"), "")}


# ── entrada ───────────────────────────────────────────────────────────
@bp.route("/")
def inicio():
    return redirect(url_for("brasil.mapa") if "br_user_id" in session else url_for("brasil.entrar"))


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    erro = None
    if request.method == "POST":
        st, d = api("POST", "/login", json={"email": request.form.get("email", ""), "senha": request.form.get("senha", "")})
        if st == 200:
            _entrar(d)
            return redirect(url_for("brasil.mapa"))
        erro = d.get("detail", "Não foi possível entrar")
    return render_template("brasil/entrar.html", erro=erro, dev_login=dev_login_ligado())


@bp.route("/dev-login/<perfil>")
def dev_login(perfil):
    """FR-005: login de teste sem senha, só com BRASIL_DEV_LOGIN=1."""
    if not dev_login_ligado() or perfil not in PERFIS:
        abort(404)
    st, d = api("POST", f"/dev/usuario/{perfil}")
    if st != 200:
        abort(st if st in (404, 503) else 502)
    _entrar(d)
    return redirect(url_for("brasil.mapa"))


@bp.route("/sair")
def sair():
    for k in ("br_user_id", "br_role", "br_nome"):
        session.pop(k, None)
    return redirect(url_for("brasil.entrar"))


# ── páginas ───────────────────────────────────────────────────────────
@bp.route("/mapa")
@exige_login()
def mapa():
    return render_template("brasil/mapa.html")


@bp.route("/perfil")
@exige_login("volunteer", "org")
def perfil():
    st, u = api("GET", f"/usuarios/{session['br_user_id']}")
    _, insc = api("GET", f"/usuarios/{session['br_user_id']}/inscricoes")
    return render_template("brasil/perfil.html", u=u if st == 200 else {}, inscricoes=insc if isinstance(insc, list) else [])


@bp.route("/admin")
@exige_login("admin")
def admin():
    return render_template("brasil/admin.html")


@bp.route("/ong")
@exige_login("org")
def ong():
    st, painel = api("GET", f"/ong/{session['br_user_id']}/painel")
    _, crises = api("GET", "/crises")
    crises = sorted(crises if isinstance(crises, list) else [], key=lambda c: (-c["severity"], c["title"]))
    return render_template("brasil/ong.html", p=painel if st == 200 else {}, crises=crises,
                           crise_escolhida=request.args.get("crise", ""))


@bp.route("/ong/campanhas/<int:cid>")
@exige_login("org")
def ong_campanha(cid):
    st, c = api("GET", f"/campanhas/{cid}")
    if st != 200 or c.get("org_id") != session["br_user_id"]:
        abort(404)
    _, na = api("GET", f"/campanhas/{cid}/voluntarios")
    _, disp = api("GET", "/voluntarios/disponiveis", params={"crisis_id": c["crisis_id"], "raio_km": 1500})
    ja = {v["volunteer_id"] for v in na} if isinstance(na, list) else set()
    disp = [v for v in disp if v["id"] not in ja] if isinstance(disp, list) else []
    return render_template("brasil/ong_campanha.html", c=c, na_campanha=na if isinstance(na, list) else [], disponiveis=disp)


@bp.route("/campanhas")
@exige_login("volunteer")
def minhas_campanhas():
    _, lista = api("GET", f"/voluntario/{session['br_user_id']}/campanhas")
    return render_template("brasil/campanhas.html", campanhas=lista if isinstance(lista, list) else [])


@bp.route("/malha.js")
def malha_js():
    """Malha IBGE vinda da API, servida como script e guardada em memória (muda só com o deploy)."""
    if "js" not in _malha_cache:
        try:
            r = requests.get(f"{API}/brasil/malha", headers=cabecalhos(), timeout=60)
            r.raise_for_status()
        except requests.RequestException:
            return Response("window.MALHA=null;", mimetype="application/javascript", status=503)
        _malha_cache["js"] = b"window.MALHA=" + r.content + b";"
    return Response(_malha_cache["js"], mimetype="application/javascript",
                    headers={"Cache-Control": "public, max-age=86400"})


# ── JSON usado pelas páginas (o usuário vem da sessão, nunca do navegador) ──
def _resposta(st, d):
    return jsonify(d), st


@bp.route("/api/crises")
@exige_login()
def api_crises():
    return _resposta(*api("GET", "/crises"))


@bp.route("/api/voluntarios-por-municipio")
@exige_login()
def api_voluntarios():
    return _resposta(*api("GET", "/voluntarios/por-municipio"))


@bp.route("/api/inscricoes")
@exige_login()
def api_inscricoes():
    return _resposta(*api("GET", f"/usuarios/{session['br_user_id']}/inscricoes"))


@bp.route("/api/crises/<crisis_id>/<acao>", methods=["POST"])
@exige_login("volunteer", "org")
def api_inscricao(crisis_id, acao):
    if acao not in ("inscrever", "cancelar"):
        abort(404)
    return _resposta(*api("POST", f"/crises/{crisis_id}/{acao}", json={"user_id": session["br_user_id"]}))


@bp.route("/api/perfil", methods=["PUT"])
@exige_login("volunteer", "org")
def api_perfil():
    return _resposta(*api("PUT", f"/usuarios/{session['br_user_id']}", json=request.get_json(silent=True) or {}))


@bp.route("/api/ingestao", methods=["POST"])
@exige_login("admin")
def api_ingestao():
    return _resposta(*api("POST", "/ingestao", timeout=300))


@bp.route("/api/ingestao/status")
@exige_login("admin")
def api_ingestao_status():
    return _resposta(*api("GET", "/ingestao/status"))


# ── campanhas (F2) ────────────────────────────────────────────────────
@bp.route("/api/campanhas", methods=["POST"])
@exige_login("org")
def api_criar_campanha():
    corpo = (request.get_json(silent=True) or {}) | {"org_id": session["br_user_id"]}
    return _resposta(*api("POST", "/campanhas", json=corpo))


@bp.route("/api/campanhas/<int:cid>", methods=["PUT"])
@exige_login("org")
def api_editar_campanha(cid):
    corpo = (request.get_json(silent=True) or {}) | {"org_id": session["br_user_id"]}
    return _resposta(*api("PUT", f"/campanhas/{cid}", json=corpo))


@bp.route("/api/campanhas/<int:cid>/voluntarios/<int:vid>", methods=["POST", "DELETE"])
@exige_login("org")
def api_voluntario_campanha(cid, vid):
    if request.method == "POST":
        return _resposta(*api("POST", f"/campanhas/{cid}/voluntarios", json={"org_id": session["br_user_id"], "volunteer_id": vid}))
    return _resposta(*api("DELETE", f"/campanhas/{cid}/voluntarios/{vid}", params={"org_id": session["br_user_id"]}))


@bp.route("/api/convites/<int:cv_id>", methods=["PUT"])
@exige_login("volunteer")
def api_convite(cv_id):
    status = (request.get_json(silent=True) or {}).get("status")
    return _resposta(*api("PUT", f"/convites/{cv_id}", json={"user_id": session["br_user_id"], "status": status}))


# ── IA, notícias, previsões e notificações (F3) ───────────────────────
@bp.route("/chat")
@exige_login("volunteer", "org")
def chat():
    crises = []
    if session.get("br_role") == "org":
        _, crises = api("GET", "/crises")
        crises = sorted(crises if isinstance(crises, list) else [], key=lambda c: (-c["severity"], c["title"]))[:400]
    return render_template("brasil/chat.html", crises=crises, crise_escolhida=request.args.get("crise", ""))


@bp.route("/previsoes")
@exige_login()
def previsoes():
    st, r = api("GET", "/previsoes", timeout=120)
    return render_template("brasil/previsoes.html", r=r if st == 200 else {"dados": [], "texto": r.get("detail", ""), "avisos": []})


@bp.route("/api/chat", methods=["POST"])
@exige_login("volunteer", "org")
def api_chat():
    corpo = request.get_json(silent=True) or {}
    return _resposta(*api("POST", "/chat", timeout=120, json={
        "user_id": session["br_user_id"], "mensagem": corpo.get("mensagem", ""), "crisis_id": corpo.get("crisis_id") or None}))


@bp.route("/api/admin/<parte>")
@exige_login("admin")
def api_admin(parte):
    caminhos = {"nao-verificadas": "/crises/nao-verificadas", "distribuicao": "/distribuicao", "notificacoes": "/notificacoes"}
    if parte not in caminhos:
        abort(404)
    return _resposta(*api("GET", caminhos[parte]))


@bp.route("/api/crises/<crisis_id>/verificacao", methods=["PUT"])
@exige_login("admin")
def api_verificacao(crisis_id):
    corpo = request.get_json(silent=True) or {}
    return _resposta(*api("PUT", f"/crises/{crisis_id}/verificacao", json={
        "user_id": session["br_user_id"], "acao": corpo.get("acao"), "severity": corpo.get("severity")}))


@bp.route("/api/crises/<crisis_id>/matching")
@exige_login("org", "admin")
def api_matching(crisis_id):
    return _resposta(*api("GET", f"/crises/{crisis_id}/matching"))


@bp.route("/api/crises/<crisis_id>/notificar", methods=["POST"])
@exige_login("org", "admin")
def api_notificar(crisis_id):
    limite = int((request.get_json(silent=True) or {}).get("limite", 10))
    return _resposta(*api("POST", f"/crises/{crisis_id}/notificar", json={"user_id": session["br_user_id"], "limite": limite}))
