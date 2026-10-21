"""Proteção CSRF por token na sessão (formulários e fetch).

Um token aleatório fica na sessão. Os formulários o levam num campo oculto ({% csrf_token %}) e o
fetch o leva no cabeçalho X-CSRF-Token (static/csrf.js). Todo POST/PUT/PATCH/DELETE é conferido.

CSRF_MODE escolhe o que acontece quando o token falta ou não confere:
  report   (padrão) só registra um aviso no log e deixa passar; serve para ver, em produção, se algo
           legítimo estaria sendo barrado antes de ligar a proteção.
  enforce  responde 400.
  off      não confere.
O cookie de sessão já é SameSite=Lax; o token é a segunda camada.
"""
import hmac
import logging
import os
import secrets

from flask import abort, request, session
from jinja2 import nodes
from jinja2.ext import Extension
from markupsafe import Markup

log = logging.getLogger("crisis.csrf")
CAMPO, CABECALHO = "csrf_token", "X-CSRF-Token"
METODOS = {"POST", "PUT", "PATCH", "DELETE"}


def valor() -> str:
    """Token da sessão (criado na primeira vez que alguma página o pede)."""
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


class CsrfTokenExtension(Extension):
    """Tag {% csrf_token %} dos templates: o campo oculto com o token."""
    tags = {"csrf_token"}

    def parse(self, parser):
        lineno = next(parser.stream).lineno
        return nodes.Output([self.call_method("_campo", [], lineno=lineno)], lineno=lineno)

    def _campo(self):
        return Markup('<input type="hidden" name="%s" value="%s">') % (CAMPO, valor())


def modo() -> str:
    return os.environ.get("CSRF_MODE", "report").strip().lower()


def verificar():
    if request.method not in METODOS or request.endpoint == "static":
        return None
    m = modo()
    if m == "off":
        return None
    enviado = request.headers.get(CABECALHO) or request.form.get(CAMPO) or ""
    esperado = session.get("_csrf", "")
    if esperado and hmac.compare_digest(enviado.encode(), esperado.encode()):
        return None
    log.warning("CSRF: token ausente ou inválido em %s %s (modo %s)", request.method, request.path, m)
    if m == "enforce":
        abort(400, "CSRF token ausente ou inválido")
    return None


def instalar(app):
    app.jinja_env.add_extension(CsrfTokenExtension)
    app.jinja_env.globals["csrf_value"] = valor  # para o <meta name="csrf-token"> dos layouts
    app.before_request(verificar)
