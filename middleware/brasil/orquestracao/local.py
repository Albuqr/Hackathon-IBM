"""Provedor `local`: executa os agentes do Dash Brasil por regras, sem LLM (padrão e fallback)."""
from .. import assistentes, ingestao, noticias
from ..config import Config
from .base import Provedor, Resposta


class LocalProvedor(Provedor):
    nome = "local"

    def __init__(self, cfg: Config, fontes: dict | None = None):
        self.cfg = cfg
        self.fontes = fontes  # injeção para testes

    def disponivel(self, agente: str) -> tuple[bool, str]:
        return True, ""

    def executar(self, agente: str, mensagem: str, contexto: dict) -> Resposta:
        if agente == "brasil_orchestrator":
            fontes = self.fontes or {**ingestao.fontes_padrao(), "noticias": lambda: noticias.coletar(self.cfg)}
            rel = ingestao.executar(self.cfg, fontes=fontes)
            ok = [f for f, r in rel["fontes"].items() if r["ok"]]
            return Resposta(f"Ingestão concluída: {rel['gravadas']} crises de {len(ok)} fontes.", rel, self.nome)
        if agente == "volunteer_agent":
            return Resposta(assistentes.texto_recomendacao(contexto["recomendacoes"]), contexto["recomendacoes"], self.nome)
        if agente == "assistant_agent":
            return Resposta(assistentes.texto_plano(contexto["plano"]), contexto["plano"], self.nome)
        if agente == "prediction_agent":
            prev = contexto["previsoes"]
            texto = (f"{len(prev)} municípios com risco de nova crise nos próximos 7–30 dias, pela recorrência dos últimos 30 dias."
                     if prev else "Sem recorrência suficiente nos últimos 30 dias para prever riscos.")
            return Resposta(texto, prev, self.nome)
        raise ValueError(f"agente desconhecido: {agente}")
