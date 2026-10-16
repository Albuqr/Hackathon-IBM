"""Interface única dos provedores de orquestração (ADR 0003, FR-028)."""
import os
from dataclasses import dataclass, field
from typing import Any

import yaml

AGENTES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "agents")


@dataclass
class Resposta:
    texto: str
    dados: Any = None
    provedor: str = "local"
    avisos: list[str] = field(default_factory=list)


class ProvedorIndisponivel(RuntimeError):
    """O provedor não pode atender este pedido (sem credencial, recusa, erro da API)."""


class Provedor:
    """Para criar um provedor novo: herde, implemente os dois métodos e registre em PROVEDORES."""
    nome = "base"

    def disponivel(self, agente: str) -> tuple[bool, str]:
        raise NotImplementedError

    def executar(self, agente: str, mensagem: str, contexto: dict) -> Resposta:
        raise NotImplementedError


def definicao_agente(agente: str) -> dict:
    """Lê agents/<agente>.yaml — a mesma definição serve a todos os provedores."""
    with open(os.path.join(AGENTES_DIR, f"{agente}.yaml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)
