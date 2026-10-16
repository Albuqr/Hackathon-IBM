"""Provedor `claude`: executa os agentes do Dash Brasil pela Claude API (SDK oficial `anthropic`).

As instruções vêm do mesmo agents/<agente>.yaml. O orquestrador usa tool use com uma ferramenta
que roda a ingestão real; os agentes de conversa recebem o contexto calculado pelas regras locais.
"""
import json
import os

from .. import ingestao, noticias
from ..config import Config
from .base import Provedor, ProvedorIndisponivel, Resposta, definicao_agente

MAX_TURNOS = 6

FERRAMENTA_INGESTAO = {
    "name": "executar_ingestao",
    "description": ("Coleta as fontes indicadas, mantém só eventos no Brasil, atribui o município IBGE e grava no banco "
                    "do Dash Brasil. Devolve o relatório por fonte (ok/erro e nº de eventos)."),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "fontes": {"type": "array", "items": {"type": "string", "enum": list(ingestao.FONTES_BR + ingestao.FONTES_GLOBAIS)}},
        },
        "required": ["fontes"],
        "additionalProperties": False,
    },
}


class ClaudeProvedor(Provedor):
    nome = "claude"

    def __init__(self, cfg: Config, cliente=None, fontes: dict | None = None):
        self.cfg = cfg
        self._cliente = cliente
        self.fontes = fontes  # injeção para testes

    def disponivel(self, agente: str) -> tuple[bool, str]:
        if self._cliente is not None:
            return True, ""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return False, "sem ANTHROPIC_API_KEY"
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False, "pacote anthropic não instalado (pip install anthropic)"
        return True, ""

    def cliente(self):
        if self._cliente is None:
            import anthropic
            self._cliente = anthropic.Anthropic()
        return self._cliente

    def _criar(self, **kw):
        # Recusa de segurança: o servidor tenta outro modelo antes de recusar ("default" escolhe pela categoria).
        resp = self.cliente().beta.messages.create(
            model=self.cfg.claude_modelo, max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)
        if resp.stop_reason == "refusal":
            raise ProvedorIndisponivel("claude recusou o pedido")
        return resp

    @staticmethod
    def _texto(resp) -> str:
        return "\n".join(b.text for b in resp.content if b.type == "text").strip()

    def executar(self, agente: str, mensagem: str, contexto: dict) -> Resposta:
        try:
            sistema = definicao_agente(agente)["instructions"]
            if agente == "brasil_orchestrator":
                return self._orquestrar(sistema, mensagem)
            conteudo = f"{mensagem}\n\nContexto (JSON):\n{json.dumps(contexto, ensure_ascii=False, default=str)}"
            resp = self._criar(system=sistema, messages=[{"role": "user", "content": conteudo}])
            dados = next(iter(contexto.values())) if len(contexto) == 1 else contexto
            return Resposta(self._texto(resp) or "(sem resposta)", dados, self.nome)
        except ProvedorIndisponivel:
            raise
        except Exception as e:  # erro de API, rede ou SDK: a camada cai para o provedor local
            raise ProvedorIndisponivel(f"claude falhou: {type(e).__name__}: {e}") from e

    def _orquestrar(self, sistema: str, mensagem: str) -> Resposta:
        fontes_disp = self.fontes or {**ingestao.fontes_padrao(), "noticias": lambda: noticias.coletar(self.cfg)}
        mensagens = [{"role": "user", "content": mensagem + "\nUse a ferramenta executar_ingestao para coletar e gravar."}]
        relatorio = {"fontes": {}, "gravadas": 0, "sem_municipio": 0, "segundos": 0.0}
        for _ in range(MAX_TURNOS):
            resp = self._criar(system=sistema, tools=[FERRAMENTA_INGESTAO], messages=mensagens)
            chamadas = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not chamadas:
                return Resposta(self._texto(resp) or "Ingestão concluída.", relatorio, self.nome)
            mensagens.append({"role": "assistant", "content": resp.content})
            resultados = []
            for ch in chamadas:
                pedidas = [f for f in ch.input.get("fontes", []) if f in fontes_disp]
                rel = ingestao.executar(self.cfg, fontes={f: fontes_disp[f] for f in pedidas})
                relatorio["fontes"].update(rel["fontes"])
                relatorio["gravadas"] += rel["gravadas"]
                relatorio["sem_municipio"] += rel["sem_municipio"]
                relatorio["segundos"] = round(relatorio["segundos"] + rel["segundos"], 1)
                resultados.append({"type": "tool_result", "tool_use_id": ch.id, "content": json.dumps(rel, ensure_ascii=False)})
            mensagens.append({"role": "user", "content": resultados})
        return Resposta("Ingestão concluída (limite de turnos atingido).", relatorio, self.nome)
