"""Provedor `watsonx`: usa o IBM watsonx Orchestrate atual (call_orchestrate do middleware/main.py)."""
import json
import os

from ..config import Config
from .base import Provedor, ProvedorIndisponivel, Resposta

# agente → variável de ambiente com o ID do agente publicado no watsonx Orchestrate
IDS = {
    "brasil_orchestrator": "BRASIL_ORCHESTRATOR_AGENT_ID",
    "volunteer_agent": "VOLUNTEER_AGENT_ID",
    "assistant_agent": "ASSISTANT_AGENT_ID",
    "prediction_agent": "BRASIL_PREDICTION_AGENT_ID",
}


class WatsonxProvedor(Provedor):
    nome = "watsonx"

    def __init__(self, cfg: Config, chamar=None):
        self.cfg = cfg
        self._chamar = chamar

    def disponivel(self, agente: str) -> tuple[bool, str]:
        faltam = [v for v in ("WO_API_KEY", "WO_INSTANCE") if not os.environ.get(v)]
        if agente in IDS and not os.environ.get(IDS[agente]):
            faltam.append(IDS[agente])
        return (not faltam, f"sem {', '.join(faltam)}" if faltam else "")

    def executar(self, agente: str, mensagem: str, contexto: dict) -> Resposta:
        chamar = self._chamar
        if chamar is None:
            from middleware.main import call_orchestrate as chamar  # import tardio: main.py inclui este pacote
        if agente == "brasil_orchestrator":
            api = os.environ.get("BRASIL_API_URL", "http://localhost:8000")
            mensagem = f"Colete as crises do Brasil e salve em {api}"
        else:
            mensagem = f"{mensagem}\n\nContexto (JSON):\n{json.dumps(contexto, ensure_ascii=False, default=str)}"
        res = chamar(mensagem, agent_id=os.environ[IDS[agente]])
        if not isinstance(res, dict) or res.get("error"):
            raise ProvedorIndisponivel(f"watsonx falhou: {res.get('error') if isinstance(res, dict) else res}")
        texto = res.get("response") or res.get("content") or json.dumps(res, ensure_ascii=False)[:2000]
        return Resposta(str(texto), res, self.nome)
