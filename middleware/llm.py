"""Camada neutra de LLM: único módulo que conhece o SDK do provedor (hoje só a Anthropic/Claude).

Quem chama (agentes.py) usa apenas os tipos abaixo; a conversão para tool_use/tool_result
acontece só aqui. Configuração somente por variáveis de ambiente:
  ANTHROPIC_API_KEY     chave (lida pelo próprio SDK; nunca em arquivo)
  CRISIS_LLM_MODELO     modelo (padrão: claude-haiku-5-5)
  CRISIS_LLM_MAX_TOKENS teto de tokens da resposta (padrão: 1024)
  CRISIS_LLM_TIMEOUT    timeout em segundos (padrão: 30)
Qualquer falha do provedor vira LLMIndisponivel; nenhum tipo de exceção do SDK vaza.
"""
import os
from dataclasses import dataclass, field

MODELO_PADRAO = "claude-haiku-5-5"
MAX_TOKENS_PADRAO = 1024
TIMEOUT_PADRAO = 30.0


class LLMIndisponivel(Exception):
    """Provedor ausente, sem chave, fora do ar, lento, limitado ou recusando a chamada."""


@dataclass
class Mensagem:
    papel: str  # "user" | "assistant"
    texto: str


@dataclass
class ChamadaFerramenta:
    id: str
    nome: str
    args: dict = field(default_factory=dict)


@dataclass
class ResultadoFerramenta:
    id: str
    conteudo: str
    erro: bool = False


@dataclass
class TurnoResultados:
    """Turno do usuário que devolve os resultados das ferramentas pedidas no turno anterior."""
    resultados: list = field(default_factory=list)


@dataclass
class RespostaLLM:
    """Turno do assistente: texto final e/ou chamadas de ferramenta (também entra no histórico)."""
    texto: str = ""
    chamadas: list = field(default_factory=list)


@dataclass
class EspecFerramenta:
    nome: str
    descricao: str
    schema_json: dict = field(default_factory=lambda: {"type": "object", "properties": {}})


# ---------- conversão neutro <-> Anthropic (funções puras) ----------

def para_anthropic_mensagens(historico) -> list[dict]:
    msgs = []
    for item in historico:
        if isinstance(item, Mensagem):
            msgs.append({"role": item.papel, "content": item.texto})
        elif isinstance(item, RespostaLLM):
            blocos = []
            if item.texto:
                blocos.append({"type": "text", "text": item.texto})
            blocos += [{"type": "tool_use", "id": c.id, "name": c.nome, "input": c.args} for c in item.chamadas]
            msgs.append({"role": "assistant", "content": blocos})
        elif isinstance(item, TurnoResultados):
            blocos = []
            for r in item.resultados:
                bloco = {"type": "tool_result", "tool_use_id": r.id, "content": r.conteudo}
                if r.erro:
                    bloco["is_error"] = True
                blocos.append(bloco)
            msgs.append({"role": "user", "content": blocos})
        else:
            raise TypeError(f"item de histórico desconhecido: {type(item).__name__}")
    return msgs


def para_anthropic_ferramentas(ferramentas) -> list[dict]:
    return [{"name": f.nome, "description": f.descricao, "input_schema": f.schema_json} for f in ferramentas]


def de_anthropic_resposta(resp) -> RespostaLLM:
    textos, chamadas = [], []
    for bloco in getattr(resp, "content", None) or []:
        tipo = getattr(bloco, "type", None)
        if tipo == "text":
            textos.append(bloco.text)
        elif tipo == "tool_use":
            chamadas.append(ChamadaFerramenta(id=bloco.id, nome=bloco.name, args=dict(bloco.input or {})))
    return RespostaLLM(texto="".join(textos), chamadas=chamadas)


# ---------- configuração ----------

def _env_num(nome: str, padrao, tipo):
    try:
        v = tipo(os.environ.get(nome, ""))
        return v if v > 0 else padrao
    except ValueError:
        return padrao


def modelo() -> str:
    return os.environ.get("CRISIS_LLM_MODELO") or MODELO_PADRAO


# ---------- provedor Anthropic ----------

class ProvedorAnthropic:
    def __init__(self, cliente=None):
        self._cliente = cliente  # injeção para testes (objeto com .messages.create)

    def _obter_cliente(self):
        if self._cliente is None:
            try:
                import anthropic  # import preguiçoso: o pacote pode não estar instalado
            except ImportError:
                raise LLMIndisponivel("pacote 'anthropic' não instalado") from None
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise LLMIndisponivel("ANTHROPIC_API_KEY não definida")
            self._cliente = anthropic.Anthropic(timeout=_env_num("CRISIS_LLM_TIMEOUT", TIMEOUT_PADRAO, float))
        return self._cliente

    def completar(self, sistema, historico, ferramentas=()):
        cliente = self._obter_cliente()
        args = dict(model=modelo(), max_tokens=_env_num("CRISIS_LLM_MAX_TOKENS", MAX_TOKENS_PADRAO, int),
                    messages=para_anthropic_mensagens(historico))
        if sistema:
            args["system"] = sistema
        if ferramentas:
            args["tools"] = para_anthropic_ferramentas(ferramentas)
        try:
            resp = cliente.messages.create(**args)
        except Exception as e:  # rede, auth, rate limit, timeout: nada do SDK vaza
            raise LLMIndisponivel(f"falha do provedor: {type(e).__name__}") from None
        return de_anthropic_resposta(resp)


# ---------- API pública ----------

_provedor = None
_padrao = None  # ProvedorAnthropic reutilizado (mantém o cliente HTTP)


def definir_provedor(obj) -> None:
    """Injeta um provedor (objeto com .completar(sistema, historico, ferramentas)); None volta ao padrão."""
    global _provedor
    _provedor = obj


def disponivel() -> bool:
    """True se há provedor injetado, ou o pacote anthropic está instalado e ANTHROPIC_API_KEY definida."""
    if _provedor is not None:
        return True
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def completar(sistema: str, historico, ferramentas=(), *, provedor=None) -> RespostaLLM:
    """Uma rodada: devolve RespostaLLM com texto OU chamadas de ferramenta. Levanta LLMIndisponivel."""
    global _padrao
    if provedor is None and _provedor is None and _padrao is None:
        _padrao = ProvedorAnthropic()
    p = provedor or _provedor or _padrao
    try:
        return p.completar(sistema, list(historico), list(ferramentas))
    except LLMIndisponivel:
        raise
    except Exception as e:
        raise LLMIndisponivel(f"falha do provedor: {type(e).__name__}") from None
