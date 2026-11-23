"""Provedor de LLM falso e roteirizável para testes (sem rede)."""
from middleware.llm import ChamadaFerramenta, RespostaLLM


def pede(nome, args=None, id="t1", texto=""):
    return RespostaLLM(texto=texto, chamadas=[ChamadaFerramenta(id=id, nome=nome, args=args or {})])


def diz(texto):
    return RespostaLLM(texto=texto)


class ProvedorFalso:
    """Devolve as respostas do roteiro em ordem (se for Exception, levanta); registra as chamadas."""

    def __init__(self, roteiro):
        self.roteiro = list(roteiro)
        self.chamadas = []  # (sistema, historico copiado, ferramentas)

    def completar(self, sistema, historico, ferramentas=()):
        self.chamadas.append((sistema, list(historico), list(ferramentas)))
        if not self.roteiro:
            raise AssertionError("roteiro esgotado")
        r = self.roteiro.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
