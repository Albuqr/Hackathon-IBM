"""Rotas de IA, notícias, matching e notificações do Dash Brasil (FR-024–FR-035)."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import assistentes, db, ingestao, notificacoes, orquestracao
from .config import Config


class Verificacao(BaseModel):
    user_id: int
    acao: str
    severity: float | None = Field(None, ge=1, le=5)


class Chat(BaseModel):
    user_id: int
    mensagem: str = Field(min_length=1, max_length=2000)
    crisis_id: str | None = None


class Notificar(BaseModel):
    user_id: int
    limite: int = Field(10, ge=1, le=100)


def criar_router(cfg: Config) -> APIRouter:
    r = APIRouter()

    def papel(conn, uid: int) -> str:
        u = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
        if not u:
            raise HTTPException(404, "Usuário não encontrado")
        return u["role"]

    def resposta(res: orquestracao.Resposta) -> dict:
        return {"texto": res.texto, "dados": res.dados, "provedor": res.provedor, "avisos": res.avisos}

    # ── ingestão pelo orquestrador (FR-027, FR-028) ───────────────────
    @r.post("/ingestao")
    def disparar_ingestao():
        res = orquestracao.executar(cfg, "brasil_orchestrator", "Colete as crises do Brasil e salve no banco do Dash Brasil.")
        rel = res.dados if isinstance(res.dados, dict) and "fontes" in res.dados else {"fontes": {}, "gravadas": 0, "segundos": 0}
        return {**rel, "texto": res.texto, "provedor": res.provedor, "avisos": res.avisos}

    @r.post("/eventos")
    def salvar_eventos(eventos: list[dict]):
        """Usado pela ferramenta br_salvar_eventos (orquestrador no watsonx)."""
        por_fonte: dict[str, list] = {}
        for e in eventos:
            por_fonte.setdefault(str(e.get("source") or "externa"), []).append(e)
        return ingestao.executar(cfg, fontes={k: (lambda v=v: v) for k, v in por_fonte.items()})

    # ── verificação de crises de notícia (FR-025) ─────────────────────
    @r.get("/crises/nao-verificadas")
    def nao_verificadas():
        conn = db.conectar(cfg)
        try:
            return [dict(x) for x in conn.execute(
                """SELECT id, title, severity, crisis_type, uf, municipio_ibge, link_fonte, visto_em, expira_em
                   FROM crises WHERE verificacao='nao_verificada' AND (expira_em IS NULL OR expira_em > ?)
                   ORDER BY visto_em DESC""", (datetime.now(timezone.utc).isoformat(timespec="seconds"),))]
        finally:
            conn.close()

    @r.put("/crises/{crisis_id}/verificacao")
    def verificar(crisis_id: str, v: Verificacao):
        if v.acao not in ("confirmar", "descartar"):
            raise HTTPException(422, "Ação inválida; use confirmar ou descartar")
        conn = db.conectar(cfg)
        try:
            if papel(conn, v.user_id) != "admin":
                raise HTTPException(403, "Só o admin confirma ou descarta crises de notícia")
            c = conn.execute("SELECT verificacao FROM crises WHERE id=?", (crisis_id,)).fetchone()
            if not c:
                raise HTTPException(404, "Crise não encontrada")
            if v.acao == "confirmar":
                conn.execute("UPDATE crises SET verificacao='verificada', expira_em=NULL, severity=COALESCE(?, severity) WHERE id=?",
                             (v.severity, crisis_id))
            else:
                conn.execute("UPDATE crises SET verificacao='descartada' WHERE id=?", (crisis_id,))
            conn.commit()
            return dict(conn.execute("SELECT id, verificacao, severity, expira_em FROM crises WHERE id=?", (crisis_id,)).fetchone())
        finally:
            conn.close()

    # ── chat (FR-030, FR-031) ─────────────────────────────────────────
    @r.post("/chat")
    def chat(c: Chat):
        conn = db.conectar(cfg)
        try:
            p = papel(conn, c.user_id)
        finally:
            conn.close()
        if p == "volunteer":
            ctx = {"recomendacoes": assistentes.recomendar(cfg, c.user_id)}
            return resposta(orquestracao.executar(cfg, "volunteer_agent", c.mensagem, ctx))
        if p == "org":
            if not c.crisis_id:
                return {"texto": assistentes.texto_plano({}), "dados": {}, "provedor": "local", "avisos": []}
            ctx = {"plano": assistentes.plano_campanha(cfg, c.crisis_id)}
            return resposta(orquestracao.executar(cfg, "assistant_agent", c.mensagem, ctx))
        raise HTTPException(403, "O chat é para voluntários e ONGs")

    # ── matching e notificações (FR-032, FR-035) ─────────────────────
    @r.get("/crises/{crisis_id}/matching")
    def ver_matching(crisis_id: str, limite: int = 20):
        return assistentes.matching(cfg, crisis_id, limite)

    @r.post("/crises/{crisis_id}/notificar")
    def notificar(crisis_id: str, n: Notificar):
        conn = db.conectar(cfg)
        try:
            if papel(conn, n.user_id) not in ("org", "admin"):
                raise HTTPException(403, "Só ONGs e admins notificam voluntários")
            crise = conn.execute("SELECT * FROM crises WHERE id=?", (crisis_id,)).fetchone()
        finally:
            conn.close()
        if not crise:
            raise HTTPException(404, "Crise não encontrada")
        matches = assistentes.matching(cfg, crisis_id, n.limite)
        return {"matches": len(matches), **notificacoes.notificar(cfg, dict(crise), matches)}

    @r.get("/notificacoes")
    def fila():
        return notificacoes.pendentes(cfg)

    # ── otimização e previsões (FR-033, FR-034) ──────────────────────
    @r.get("/distribuicao")
    def distribuicao():
        return assistentes.distribuicao(cfg)

    @r.get("/previsoes")
    def previsoes():
        ctx = {"previsoes": assistentes.previsoes(cfg)}
        return resposta(orquestracao.executar(cfg, "prediction_agent", "Quais municípios têm risco de nova crise nos próximos 7–30 dias?", ctx))

    return r
