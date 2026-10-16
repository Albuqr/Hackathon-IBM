"""Orquestração trocável do Dash Brasil (ADR 0003, FR-028, FR-029).

`executar(cfg, agente, mensagem, contexto)` usa o provedor de BRASIL_ORQUESTRADOR; se ele não tiver
credencial ou falhar, roda no `local` e registra o motivo no log e nos avisos da resposta.
"""
from ..config import Config
from .base import Provedor, ProvedorIndisponivel, Resposta
from .claude import ClaudeProvedor
from .local import LocalProvedor
from .watsonx import WatsonxProvedor

PROVEDORES = {"local": LocalProvedor, "watsonx": WatsonxProvedor, "claude": ClaudeProvedor}


def executar(cfg: Config, agente: str, mensagem: str = "", contexto: dict | None = None,
             provedor: Provedor | None = None, local: Provedor | None = None) -> Resposta:
    contexto = contexto or {}
    escolhido = provedor or PROVEDORES[cfg.orquestrador](cfg)
    local = local or LocalProvedor(cfg)
    if escolhido.nome == "local":
        return escolhido.executar(agente, mensagem, contexto)
    ok, motivo = escolhido.disponivel(agente)
    if ok:
        try:
            return escolhido.executar(agente, mensagem, contexto)
        except ProvedorIndisponivel as e:
            motivo = str(e)
    aviso = f"{escolhido.nome} indisponível: {motivo}; usando local"
    print(f"[brasil] {aviso}")
    r = local.executar(agente, mensagem, contexto)
    r.avisos.append(aviso)
    return r


__all__ = ["executar", "PROVEDORES", "Provedor", "Resposta", "ProvedorIndisponivel"]
