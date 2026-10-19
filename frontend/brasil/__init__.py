"""Dash Brasil — páginas /brasil/... do frontend do Crisis Monitor (ADR 0001, ADR 0004).

Fala só com a API /brasil/... (nunca abre banco). A sessão usa chaves próprias
(br_user_id, br_role, br_nome) porque os IDs vêm do brasil.db, não do banco do Crisis.
O navegador só alcança a API pelo encaminhador (/brasil/acao/<nome>), que aplica a POLITICA.
"""
import os
from functools import wraps

from flask import (Blueprint, Response, abort, current_app, jsonify, redirect, render_template, request,
                   session, url_for)

from .api_cliente import ApiHttp
from .encaminhador import POLITICA, Recusa, encaminhar

PERFIS = {"voluntario": "volunteer", "ong": "org", "admin": "admin"}
NOME_PAPEL = {"volunteer": "Voluntário", "org": "ONG", "admin": "Admin"}

bp = Blueprint("brasil", __name__, url_prefix="/brasil",
               template_folder="templates", static_folder="static", static_url_path="/static")

_malha_cache: dict = {}


def api():
    """Adapter da API: o configurado no app (testes) ou o HTTP padrão."""
    if "BRASIL_API" not in current_app.config:
        current_app.config["BRASIL_API"] = ApiHttp(os.environ.get("API_URL", "http://localhost:8000"))
    return current_app.config["BRASIL_API"]


def como_eu(metodo: str, caminho: str, **kw):
    """Chamada à API com a identidade da sessão (páginas renderizadas no servidor)."""
    return api()(metodo, caminho, usuario=session.get("br_user_id"), **kw)


def dev_login_ligado() -> bool:
    return os.environ.get("BRASIL_DEV_LOGIN", "") == "1"


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
    nome = session.get("br_nome") or ""
    return {"br_nome": nome, "br_role": session.get("br_role"), "br_papel": NOME_PAPEL.get(session.get("br_role"), ""),
            "br_iniciais": "".join(p[0] for p in nome.split()[:2]).upper() or "?"}


# ── entrada ───────────────────────────────────────────────────────────
@bp.route("/")
def inicio():
    return redirect(url_for("brasil.mapa") if "br_user_id" in session else url_for("brasil.entrar"))


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    erro = None
    if request.method == "POST":
        st, d = api()("POST", "/login", json={"email": request.form.get("email", ""), "senha": request.form.get("senha", "")})
        if st == 200:
            _entrar(d)
            return redirect(url_for("brasil.mapa"))
        erro = d.get("detail", "Não foi possível entrar") if isinstance(d, dict) else "Não foi possível entrar"
    return render_template("brasil/entrar.html", erro=erro, dev_login=dev_login_ligado())


@bp.route("/dev-login/<perfil>")
def dev_login(perfil):
    """Login de teste sem senha, só com BRASIL_DEV_LOGIN=1."""
    if not dev_login_ligado() or perfil not in PERFIS:
        abort(404)
    st, d = api()("POST", f"/dev/usuario/{perfil}")
    if st != 200:
        abort(st if st in (404, 503) else 502)
    _entrar(d)
    return redirect(url_for("brasil.mapa"))


@bp.route("/sair")
def sair():
    for k in ("br_user_id", "br_role", "br_nome"):
        session.pop(k, None)
    return redirect(url_for("brasil.entrar"))


# ── encaminhador (FR-023) ─────────────────────────────────────────────
@bp.route("/acao/<nome>", methods=["POST"])
def acao(nome):
    if "br_user_id" not in session:
        return jsonify({"detail": "Entre para continuar"}), 401
    try:
        st, d = encaminhar(api(), nome, session.get("br_role"), session["br_user_id"], request.get_json(silent=True) or {})
    except Recusa as r:
        return jsonify({"detail": r.detalhe}), r.status
    return jsonify(d), st


# ── páginas ───────────────────────────────────────────────────────────
@bp.route("/mapa")
@exige_login()
def mapa():
    return render_template("brasil/mapa.html")


@bp.route("/perfil")
@exige_login("volunteer", "org")
def perfil():
    st, u = como_eu("GET", f"/usuarios/{session['br_user_id']}")
    return render_template("brasil/perfil.html", u=u if st == 200 else {})


@bp.route("/chat")
@exige_login("volunteer", "org")
def chat():
    """O chat agora mora no perfil (voluntário) e na página da campanha (ONG)."""
    return redirect(url_for("brasil.perfil") if session.get("br_role") == "volunteer" else url_for("brasil.ong"))


@bp.route("/campanhas")
@exige_login("volunteer")
def minhas_campanhas():
    return render_template("brasil/campanhas.html")


@bp.route("/ong")
@exige_login("org")
def ong():
    st, painel = como_eu("GET", f"/ong/{session['br_user_id']}/painel")
    return render_template("brasil/ong.html", p=painel if st == 200 else {})


@bp.route("/ong/nova")
@exige_login("org")
def ong_nova():
    crise = None
    if request.args.get("crise"):
        _, lista = como_eu("GET", "/crises")
        crise = next((c for c in lista if c["id"] == request.args["crise"]), None) if isinstance(lista, list) else None
    return render_template("brasil/ong_nova.html", crise=crise)


@bp.route("/ong/campanhas/<int:cid>")
@exige_login("org")
def ong_campanha(cid):
    st, c = como_eu("GET", f"/campanhas/{cid}")
    if st != 200:
        abort(404)
    return render_template("brasil/ong_campanha.html", c=c)


@bp.route("/admin")
@exige_login("admin")
def admin():
    return render_template("brasil/admin.html")


@bp.route("/previsoes")
@exige_login()
def previsoes():
    st, r = como_eu("GET", "/previsoes", timeout=120)
    if st != 200:
        r = {"dados": [], "texto": r.get("detail", "") if isinstance(r, dict) else "", "avisos": []}
    return render_template("brasil/previsoes.html", r=r)


@bp.route("/malha.js")
def malha_js():
    """Malha IBGE vinda da API, servida como script e guardada em memória (muda só com o deploy)."""
    if "js" not in _malha_cache:
        conteudo = api().bruto("/malha")
        if conteudo is None:
            return Response("window.MALHA=null;", mimetype="application/javascript", status=503)
        _malha_cache["js"] = b"window.MALHA=" + conteudo + b";"
    return Response(_malha_cache["js"], mimetype="application/javascript",
                    headers={"Cache-Control": "public, max-age=86400"})


__all__ = ["bp", "POLITICA"]
